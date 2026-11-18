# handlers/states/state_image_processing.py

import os
import io
import uuid
from telegram import Update
from telegram.ext import ContextTypes
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    PIL_AVAILABLE = False

import asyncio
from core.state_manager import StateCache, get_state, clear_state
from core.keyboards import get_main_menu_keyboard
from core.database import log_upload_success
import time

# Try to import rembg, but make it optional
try:
    from rembg import remove

    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False


# Semaphore to limit concurrent heavy media operations (video-to-gif, audio extraction)
MEDIA_MAX_CONCURRENT = 2
media_processing_semaphore = asyncio.Semaphore(MEDIA_MAX_CONCURRENT)

_IMG_TMP_DIR = os.path.join("downloads", "img_tmp")
_background_tasks: set[asyncio.Task] = set()

# Bounded TTL caches storing temp disk paths (never raw image bytes in RAM)
_pdf_images_cache = StateCache(max_capacity=400, default_ttl=1800.0)
_convert_images_cache = StateCache(max_capacity=400, default_ttl=1800.0)
_resize_images_cache = StateCache(max_capacity=400, default_ttl=1800.0)


def _track_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _remove_files_quietly(paths) -> None:
    if not paths:
        return
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    for p in paths:
        if p and isinstance(p, (str, os.PathLike)) and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


async def _download_image_to_disk(bot, file_id: str, prefix: str) -> str:
    os.makedirs(_IMG_TMP_DIR, exist_ok=True)
    dest_path = os.path.join(_IMG_TMP_DIR, f"{prefix}_{uuid.uuid4().hex[:10]}.img")
    tg_file = await bot.get_file(file_id)
    await tg_file.download_to_drive(dest_path)
    return dest_path


def _open_pil_image(source):
    if isinstance(source, (bytes, bytearray)):
        return Image.open(io.BytesIO(source))
    return Image.open(source)


async def handle_img_create_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle PDF creation from images"""
    chat_id = str(update.effective_chat.id)

    # Check if user sent "done" or "تمام"
    if update.message.text and update.message.text.lower() in [
        "done",
        "تمام",
        "finish",
    ]:
        pending_images = _pdf_images_cache.get(chat_id) or []
        if len(pending_images) == 0:
            await update.message.reply_text("❌ هیچ عکسی ارسال نشده است!")
            return

        await update.message.reply_text("⏳ در حال ساخت PDF...")

        pdf_path = None
        try:
            # Create PDF from images
            pdf_path = await create_pdf_from_images(pending_images, chat_id)

            # Send PDF to user
            with open(pdf_path, "rb") as pdf_file:
                await update.message.reply_document(
                    document=pdf_file,
                    filename=f"images_{chat_id}.pdf",
                    caption="✅ PDF شما آماده است!",
                )
            await log_upload_success("image_processing", chat_id)

            clear_state(chat_id)

            await update.message.reply_text(
                "✅ عملیات با موفقیت انجام شد!", reply_markup=get_main_menu_keyboard()
            )

        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ساخت PDF: {str(e)}")
            clear_state(chat_id)
        finally:
            _pdf_images_cache.pop(chat_id, None)
            _remove_files_quietly(pending_images)
            _remove_files_quietly(pdf_path)

        return

    # Handle image upload
    if update.message.photo:
        pending_images = _pdf_images_cache.get(chat_id)
        if pending_images is None:
            pending_images = []
        if len(pending_images) >= 20:
            await update.message.reply_text("❌ حداکثر 20 عکس می‌توانید ارسال کنید!")
            return

        # Download image to temp file on disk instead of holding bytes in RAM
        photo = update.message.photo[-1]
        img_path = await _download_image_to_disk(context.bot, photo.file_id, f"pdf_{chat_id}")

        pending_images.append(img_path)
        _pdf_images_cache[chat_id] = pending_images

        await update.message.reply_text(
            f"✅ عکس {len(pending_images)} دریافت شد.\n"
            f"برای ادامه عکس بعدی را ارسال کنید یا 'تمام' را بنویسید."
        )
    else:
        await update.message.reply_text(
            "❌ لطفاً یک عکس ارسال کنید یا 'تمام' را بنویسید."
        )


async def handle_img_convert_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image format conversion"""
    chat_id = str(update.effective_chat.id)

    # Check if user sent format choice
    if update.message.text:
        format_text = update.message.text.upper().strip()

        if format_text in ["PNG", "JPG", "JPEG", "WEBP", "BMP", "GIF"]:
            raw_img = _convert_images_cache.get(chat_id)
            if raw_img is None:
                await update.message.reply_text("❌ ابتدا یک عکس ارسال کنید!")
                return

            await update.message.reply_text(f"⏳ در حال تبدیل به {format_text}...")

            converted_path = None
            try:
                # Convert image
                converted_path = await convert_image_format(
                    raw_img, format_text, chat_id
                )

                # Send converted image
                with open(converted_path, "rb") as img_file:
                    await update.message.reply_document(
                        document=img_file,
                        filename=f"converted.{format_text.lower()}",
                        caption=f"✅ عکس به فرمت {format_text} تبدیل شد!",
                    )
                await log_upload_success("image_processing", chat_id)

                clear_state(chat_id)

                await update.message.reply_text(
                    "✅ عملیات با موفقیت انجام شد!",
                    reply_markup=get_main_menu_keyboard(),
                )

            except Exception as e:
                await update.message.reply_text(f"❌ خطا در تبدیل فرمت: {str(e)}")
                clear_state(chat_id)
            finally:
                _convert_images_cache.pop(chat_id, None)
                _remove_files_quietly(raw_img)
                _remove_files_quietly(converted_path)

            return

    # Handle image upload
    if update.message.photo or (
        update.message.document
        and update.message.document.mime_type.startswith("image/")
    ):
        await update.message.reply_text("⏳ در حال دریافت عکس...")

        try:
            if update.message.photo:
                file_id = update.message.photo[-1].file_id
            else:
                file_id = update.message.document.file_id

            old_path = _convert_images_cache.pop(chat_id, None)
            _remove_files_quietly(old_path)
            img_path = await _download_image_to_disk(context.bot, file_id, f"conv_{chat_id}")
            _convert_images_cache[chat_id] = img_path

            await update.message.reply_text(
                "✅ عکس دریافت شد!\n\n"
                "حالا فرمت مورد نظر را ارسال کنید:\n"
                "PNG | JPG | JPEG | WEBP | BMP | GIF"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ خطا در دریافت عکس: {str(e)}")
    else:
        await update.message.reply_text("❌ لطفاً یک عکس ارسال کنید!")


async def handle_img_resize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image resizing"""
    chat_id = str(update.effective_chat.id)

    # Check if user sent size
    if update.message.text:
        size_text = update.message.text.strip()

        raw_img = _resize_images_cache.get(chat_id)
        if raw_img is None:
            await update.message.reply_text("❌ ابتدا یک عکس ارسال کنید!")
            return

        await update.message.reply_text("⏳ در حال تغییر اندازه...")

        resized_path = None
        try:
            # Resize image
            resized_path = await resize_image(raw_img, size_text, chat_id)

            # Send resized image
            with open(resized_path, "rb") as img_file:
                await update.message.reply_document(
                    document=img_file,
                    filename="resized.png",
                    caption="✅ اندازه عکس تغییر کرد!",
                )
            await log_upload_success("image_processing", chat_id)

            _resize_images_cache.pop(chat_id, None)
            _remove_files_quietly(raw_img)
            clear_state(chat_id)

            await update.message.reply_text(
                "✅ عملیات با موفقیت انجام شد!", reply_markup=get_main_menu_keyboard()
            )

        except Exception as e:
            await update.message.reply_text(
                f"❌ خطا در تغییر اندازه: {str(e)}\n\nفرمت صحیح: 800x600 یا 50%"
            )
        finally:
            _remove_files_quietly(resized_path)

        return

    # Handle image upload
    if update.message.photo or (
        update.message.document
        and update.message.document.mime_type.startswith("image/")
    ):
        await update.message.reply_text("⏳ در حال دریافت عکس...")

        try:
            if update.message.photo:
                file_id = update.message.photo[-1].file_id
            else:
                file_id = update.message.document.file_id

            old_path = _resize_images_cache.pop(chat_id, None)
            _remove_files_quietly(old_path)
            img_path = await _download_image_to_disk(context.bot, file_id, f"resize_{chat_id}")
            _resize_images_cache[chat_id] = img_path

            await update.message.reply_text(
                "✅ عکس دریافت شد!\n\n"
                "حالا ابعاد جدید را وارد کنید:\n"
                "مثال: 800x600 یا 50%"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ خطا در دریافت عکس: {str(e)}")
    else:
        await update.message.reply_text("❌ لطفاً یک عکس ارسال کنید!")


async def handle_img_remove_bg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle background removal"""
    chat_id = str(update.effective_chat.id)

    # Check if rembg is available
    if not REMBG_AVAILABLE:
        await update.message.reply_text(
            "❌ قابلیت حذف پس‌زمینه در حال حاضر غیرفعال است.\n\n"
            "برای فعال‌سازی این قابلیت، نیاز به نصب کتابخانه rembg است:\n"
            "`pip install rembg[cpu]`"
        )
        clear_state(chat_id)
        await update.message.reply_text(
            "لطفاً از سایر قابلیت‌های پردازش تصویر استفاده کنید.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # Handle image upload
    if update.message.photo or (
        update.message.document
        and update.message.document.mime_type.startswith("image/")
    ):
        await update.message.reply_text(
            "⏳ در حال حذف پس‌زمینه... (ممکن است چند ثانیه طول بکشد)"
        )

        input_path = None
        output_path = None
        try:
            if update.message.photo:
                file_id = update.message.photo[-1].file_id
            else:
                file_id = update.message.document.file_id

            input_path = await _download_image_to_disk(context.bot, file_id, f"rmbg_{chat_id}")

            # Remove background
            output_path = await remove_background(input_path, chat_id)

            # Send result
            with open(output_path, "rb") as img_file:
                await update.message.reply_document(
                    document=img_file,
                    filename="no_background.png",
                    caption="✅ پس‌زمینه عکس حذف شد!",
                )
            await log_upload_success("image_processing", chat_id)

            clear_state(chat_id)

            await update.message.reply_text(
                "✅ عملیات با موفقیت انجام شد!", reply_markup=get_main_menu_keyboard()
            )

        except Exception as e:
            await update.message.reply_text(f"❌ خطا در حذف پس‌زمینه: {str(e)}")
            clear_state(chat_id)
        finally:
            _remove_files_quietly(input_path)
            _remove_files_quietly(output_path)
    else:
        await update.message.reply_text("❌ لطفاً یک عکس ارسال کنید!")


# Helper functions


async def create_pdf_from_images(images_sources, chat_id):
    """Create PDF from list of image paths or raw image bytes."""

    def _create_pdf():
        images = []
        try:
            for src in images_sources:
                with _open_pil_image(src) as img:
                    if img.mode != "RGB":
                        converted = img.convert("RGB")
                    else:
                        converted = img.copy()
                    images.append(converted)

            os.makedirs("downloads", exist_ok=True)
            pdf_path = f"downloads/pdf_{chat_id}_{uuid.uuid4().hex[:8]}.pdf"

            images[0].save(pdf_path, save_all=True, append_images=images[1:])
            return pdf_path
        finally:
            for im in images:
                try:
                    im.close()
                except Exception:
                    pass

    return await asyncio.to_thread(_create_pdf)


async def convert_image_format(image_source, target_format, chat_id):
    """Convert image (disk path or bytes) to target format."""

    def _convert():
        with _open_pil_image(image_source) as img:
            # Determine the save format (PIL uses JPEG not JPG)
            save_format = "JPEG" if target_format == "JPG" else target_format

            # Handle transparency for formats that don't support it
            if save_format in ["JPEG", "BMP"] and img.mode in ["RGBA", "LA"]:
                background = Image.new("RGB", img.size, (255, 255, 255))
                try:
                    if img.mode == "RGBA":
                        background.paste(img, mask=img.split()[3])
                    else:
                        background.paste(img, mask=img.split()[1])
                    out_img = background
                except Exception:
                    background.close()
                    raise
            else:
                out_img = img

            os.makedirs("downloads", exist_ok=True)
            output_path = (
                f"downloads/converted_{chat_id}_{uuid.uuid4().hex[:8]}.{target_format.lower()}"
            )
            try:
                out_img.save(output_path, format=save_format)
            finally:
                if out_img is not img:
                    out_img.close()
            return output_path

    return await asyncio.to_thread(_convert)


async def resize_image(image_source, size_text, chat_id):
    """Resize image (disk path or bytes) based on size text."""

    def _resize():
        with _open_pil_image(image_source) as img:
            if "%" in size_text:
                percent = int(size_text.replace("%", ""))
                new_width = int(img.width * percent / 100)
                new_height = int(img.height * percent / 100)
            elif "x" in size_text.lower():
                width, height = size_text.lower().split("x")
                new_width = int(width)
                new_height = int(height)
            else:
                raise ValueError("Invalid size format")

            if new_width <= 0 or new_height <= 0 or new_width > 10000 or new_height > 10000:
                raise ValueError("Invalid dimensions")

            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            os.makedirs("downloads", exist_ok=True)
            output_path = f"downloads/resized_{chat_id}_{uuid.uuid4().hex[:8]}.png"
            try:
                resized_img.save(output_path)
            finally:
                resized_img.close()
            return output_path

    return await asyncio.to_thread(_resize)


async def remove_background(image_source, chat_id):
    """Remove background from image (disk path or bytes)."""
    if not REMBG_AVAILABLE:
        raise ImportError("rembg library is not installed")

    def _remove_bg():
        with _open_pil_image(image_source) as input_img:
            output_img = remove(input_img)
            os.makedirs("downloads", exist_ok=True)
            output_path = f"downloads/no_bg_{chat_id}_{uuid.uuid4().hex[:8]}.png"
            try:
                output_img.save(output_path)
            finally:
                try:
                    output_img.close()
                except Exception:
                    pass
            return output_path

    return await asyncio.to_thread(_remove_bg)


async def handle_img_video_to_gif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video to GIF conversion"""
    chat_id = str(update.effective_chat.id)

    # Check if user sent a video, video note, or document containing a video
    video_file = None
    if update.message.video:
        video_file = update.message.video
    elif update.message.video_note:
        video_file = update.message.video_note
    elif update.message.document and (update.message.document.mime_type or "").startswith("video/"):
        video_file = update.message.document

    if not video_file:
        if update.message.text:
            await update.message.reply_text("❌ لطفاً یک ویدیو ارسال کنید.")
        return

    # Check queue status
    waiters = (
        len(media_processing_semaphore._waiters)
        if hasattr(media_processing_semaphore, "_waiters") and media_processing_semaphore._waiters
        else 0
    )
    
    in_queue = media_processing_semaphore.locked()
    if in_queue:
        status_msg = await update.message.reply_text(
            f"⏳ ربات در حال پردازش درخواست‌های دیگر است. شما در صف قرار گرفتید (نفر {waiters + 1} در صف). لطفاً صبور باشید..."
        )
    else:
        status_msg = await update.message.reply_text("⏳ درخواست شما ثبت شد. در حال اتصال به صف پردازش...")

    # Clear user state immediately so they are free to use the bot
    clear_state(chat_id)

    timestamp = int(time.time())
    os.makedirs("downloads", exist_ok=True)
    temp_video_path = f"downloads/temp_video_{chat_id}_{timestamp}"
    
    ext = ".mp4"
    if hasattr(video_file, "file_name") and video_file.file_name:
        _, file_ext = os.path.splitext(video_file.file_name)
        if file_ext:
            ext = file_ext
    temp_video_path += ext

    # Launch background task
    _track_background_task(
        background_video_to_gif(
            context,
            chat_id,
            video_file,
            status_msg,
            timestamp,
            temp_video_path,
            in_queue
        )
    )


async def background_video_to_gif(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    video_file,
    status_msg,
    timestamp: int,
    temp_video_path: str,
    in_queue: bool,
):
    try:
        async with media_processing_semaphore:
            if in_queue:
                await status_msg.edit_text("⏳ نوبت شما رسید! در حال دریافت ویدیو...")
            else:
                await status_msg.edit_text("⏳ در حال دریافت ویدیو...")
                
            file = await context.bot.get_file(video_file.file_id)
            await file.download_to_drive(temp_video_path)

            await status_msg.edit_text("⏳ در حال تبدیل ویدیو به GIF (حداکثر ۷ ثانیه اول)...")

            # Detect if it's a video note to use square scale
            is_video_note = hasattr(video_file, "length") and video_file.length is not None
            gif_path = await convert_video_to_gif(temp_video_path, chat_id, timestamp, is_video_note)

            if gif_path and os.path.exists(gif_path):
                await status_msg.edit_text("📤 تبدیل با موفقیت انجام شد! در حال ارسال...")
                with open(gif_path, "rb") as gif_file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=gif_file,
                        filename=f"video_{timestamp}.gif",
                        caption="✅ ویدیوی شما به GIF تبدیل شد!",
                    )
                
                await log_upload_success("image_processing", chat_id)
                
                try:
                    os.remove(gif_path)
                except Exception:
                    pass
                
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            else:
                await status_msg.edit_text("❌ خطا در تبدیل ویدیو به GIF. لطفاً ویدیوی دیگری را امتحان کنید.")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="بازگشت به منوی اصلی:",
                    reply_markup=get_main_menu_keyboard(),
                )

    except Exception as e:
        print(f"Error converting video to GIF in background: {e}")
        try:
            await status_msg.edit_text(f"❌ خطا در پردازش ویدیو: {str(e)}")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ خطا در پردازش ویدیو: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="بازگشت به منوی اصلی:",
            reply_markup=get_main_menu_keyboard(),
        )
    finally:
        if os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except Exception:
                pass


async def _run_ffmpeg(cmd: list[str], timeout_sec: float = 180.0) -> bool:
    """Run an ffmpeg command asynchronously with timeout and forced termination on hang."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(process.communicate(), timeout=timeout_sec)
        return process.returncode == 0
    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        return False


async def convert_video_to_gif(video_path: str, chat_id: str, timestamp: int, is_video_note: bool = False) -> str:
    """Convert video to GIF using ffmpeg with optimization"""
    gif_path = f"downloads/gif_{chat_id}_{timestamp}.gif"
    
    # 280px for standard, 240x240 for circular video notes
    scale_filter = "scale=240:240" if is_video_note else "scale=280:-1"
    
    # Optimize GIF generation:
    # 1. Limit output duration to max 7 seconds (-t 7) to keep size extremely small.
    # 2. Use 20 fps for smooth animation.
    # 3. Limit color palette to 128 colors.
    # 4. Use Bayer dithering with rectangle diff mode for optimal GIF compression.
    cmd = [
        "ffmpeg",
        "-y",
        "-t", "7",
        "-i", video_path,
        "-vf", f"fps=20,{scale_filter}:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
        gif_path,
    ]
    
    try:
        if await _run_ffmpeg(cmd, timeout_sec=180.0) and os.path.exists(gif_path):
            return gif_path
    except Exception as e:
        print(f"ffmpeg gif conversion error: {e}")
    return ""


async def handle_img_extract_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle audio extraction from video"""
    chat_id = str(update.effective_chat.id)

    video_file = None
    if update.message.video:
        video_file = update.message.video
    elif update.message.video_note:
        video_file = update.message.video_note
    elif update.message.audio:
        video_file = update.message.audio
    elif update.message.voice:
        video_file = update.message.voice
    elif update.message.document and (
        (update.message.document.mime_type or "").startswith("video/") 
        or (update.message.document.mime_type or "").startswith("audio/")
    ):
        video_file = update.message.document

    if not video_file:
        if update.message.text:
            await update.message.reply_text("❌ لطفاً یک ویدیو یا فایل رسانه‌ای ارسال کنید.")
        return

    # Check queue status
    waiters = (
        len(media_processing_semaphore._waiters)
        if hasattr(media_processing_semaphore, "_waiters") and media_processing_semaphore._waiters
        else 0
    )
    
    in_queue = media_processing_semaphore.locked()
    if in_queue:
        status_msg = await update.message.reply_text(
            f"⏳ ربات در حال پردازش درخواست‌های دیگر است. شما در صف قرار گرفتید (نفر {waiters + 1} در صف). لطفاً صبور باشید..."
        )
    else:
        status_msg = await update.message.reply_text("⏳ درخواست شما ثبت شد. در حال اتصال به صف پردازش...")

    # Clear user state immediately so they are free to use the bot
    clear_state(chat_id)

    timestamp = int(time.time())
    os.makedirs("downloads", exist_ok=True)
    temp_media_path = f"downloads/temp_media_{chat_id}_{timestamp}"
    
    ext = ".mp4"
    if hasattr(video_file, "file_name") and video_file.file_name:
        _, file_ext = os.path.splitext(video_file.file_name)
        if file_ext:
            ext = file_ext
    temp_media_path += ext

    # Launch background task
    _track_background_task(
        background_extract_audio(
            context,
            chat_id,
            video_file,
            status_msg,
            timestamp,
            temp_media_path,
            in_queue
        )
    )


async def background_extract_audio(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    video_file,
    status_msg,
    timestamp: int,
    temp_media_path: str,
    in_queue: bool,
):
    try:
        async with media_processing_semaphore:
            if in_queue:
                await status_msg.edit_text("⏳ نوبت شما رسید! در حال دریافت رسانه...")
            else:
                await status_msg.edit_text("⏳ در حال دریافت رسانه...")
                
            file = await context.bot.get_file(video_file.file_id)
            await file.download_to_drive(temp_media_path)

            await status_msg.edit_text("⏳ در حال استخراج صدا...")

            mp3_path = await extract_audio_from_video(temp_media_path, chat_id, timestamp)

            if mp3_path and os.path.exists(mp3_path):
                await status_msg.edit_text("📤 استخراج صوتی تکمیل شد! در حال ارسال...")
                with open(mp3_path, "rb") as mp3_file:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=mp3_file,
                        filename=f"audio_{timestamp}.mp3",
                        title="استخراج شده از ویدیو",
                        performer="ربات پردازش رسانه",
                        caption="✅ صدای استخراج شده با موفقیت آماده شد!",
                    )
                
                await log_upload_success("image_processing", chat_id)
                
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass
                
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            else:
                await status_msg.edit_text("❌ خطا در استخراج صدا از ویدیو.")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="بازگشت به منوی اصلی:",
                    reply_markup=get_main_menu_keyboard(),
                )

    except Exception as e:
        print(f"Error extracting audio in background: {e}")
        try:
            await status_msg.edit_text(f"❌ خطا در پردازش رسانه: {str(e)}")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ خطا در پردازش رسانه: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="بازگشت به منوی اصلی:",
            reply_markup=get_main_menu_keyboard(),
        )
    finally:
        if os.path.exists(temp_media_path):
            try:
                os.remove(temp_media_path)
            except Exception:
                pass


async def extract_audio_from_video(media_path: str, chat_id: str, timestamp: int) -> str:
    """Extract audio to MP3 using ffmpeg"""
    mp3_path = f"downloads/audio_{chat_id}_{timestamp}.mp3"
    
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        media_path,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-q:a",
        "2",
        mp3_path,
    ]
    
    try:
        if await _run_ffmpeg(cmd, timeout_sec=180.0) and os.path.exists(mp3_path):
            return mp3_path
    except Exception as e:
        print(f"ffmpeg audio extraction error: {e}")
    return ""


# Made with Bob
