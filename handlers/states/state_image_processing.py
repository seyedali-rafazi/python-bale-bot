# handlers/states/state_image_processing.py

import os
import io
from telegram import Update
from telegram.ext import ContextTypes
from PIL import Image
import asyncio
from core.state_manager import get_state, clear_state
from core.keyboards import get_main_menu_keyboard

# Try to import rembg, but make it optional
try:
    from rembg import remove

    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False
    print("⚠️ rembg not available. Background removal feature will be disabled.")


async def handle_img_create_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle PDF creation from images"""
    chat_id = str(update.effective_chat.id)

    # Initialize user data if not exists
    if "pdf_images" not in context.user_data:
        context.user_data["pdf_images"] = []

    # Check if user sent "done" or "تمام"
    if update.message.text and update.message.text.lower() in [
        "done",
        "تمام",
        "finish",
    ]:
        if len(context.user_data["pdf_images"]) == 0:
            await update.message.reply_text("❌ هیچ عکسی ارسال نشده است!")
            return

        await update.message.reply_text("⏳ در حال ساخت PDF...")

        try:
            # Create PDF from images
            pdf_path = await create_pdf_from_images(
                context.user_data["pdf_images"], chat_id
            )

            # Send PDF to user
            with open(pdf_path, "rb") as pdf_file:
                await update.message.reply_document(
                    document=pdf_file,
                    filename=f"images_{chat_id}.pdf",
                    caption="✅ PDF شما آماده است!",
                )

            # Cleanup
            os.remove(pdf_path)
            context.user_data["pdf_images"] = []
            clear_state(chat_id)

            await update.message.reply_text(
                "✅ عملیات با موفقیت انجام شد!", reply_markup=get_main_menu_keyboard()
            )

        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ساخت PDF: {str(e)}")
            context.user_data["pdf_images"] = []
            clear_state(chat_id)

        return

    # Handle image upload
    if update.message.photo:
        if len(context.user_data["pdf_images"]) >= 20:
            await update.message.reply_text("❌ حداکثر 20 عکس می‌توانید ارسال کنید!")
            return

        # Download image
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        context.user_data["pdf_images"].append(image_bytes)

        await update.message.reply_text(
            f"✅ عکس {len(context.user_data['pdf_images'])} دریافت شد.\n"
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
            if "convert_image" not in context.user_data:
                await update.message.reply_text("❌ ابتدا یک عکس ارسال کنید!")
                return

            await update.message.reply_text(f"⏳ در حال تبدیل به {format_text}...")

            try:
                # Convert image
                converted_path = await convert_image_format(
                    context.user_data["convert_image"], format_text, chat_id
                )

                # Send converted image
                with open(converted_path, "rb") as img_file:
                    await update.message.reply_document(
                        document=img_file,
                        filename=f"converted.{format_text.lower()}",
                        caption=f"✅ عکس به فرمت {format_text} تبدیل شد!",
                    )

                # Cleanup
                os.remove(converted_path)
                del context.user_data["convert_image"]
                clear_state(chat_id)

                await update.message.reply_text(
                    "✅ عملیات با موفقیت انجام شد!",
                    reply_markup=get_main_menu_keyboard(),
                )

            except Exception as e:
                await update.message.reply_text(f"❌ خطا در تبدیل فرمت: {str(e)}")
                clear_state(chat_id)

            return

    # Handle image upload
    if update.message.photo or (
        update.message.document
        and update.message.document.mime_type.startswith("image/")
    ):
        await update.message.reply_text("⏳ در حال دریافت عکس...")

        try:
            if update.message.photo:
                photo = update.message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
            else:
                file = await context.bot.get_file(update.message.document.file_id)

            image_bytes = await file.download_as_bytearray()
            context.user_data["convert_image"] = image_bytes

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

        if "resize_image" not in context.user_data:
            await update.message.reply_text("❌ ابتدا یک عکس ارسال کنید!")
            return

        await update.message.reply_text("⏳ در حال تغییر اندازه...")

        try:
            # Resize image
            resized_path = await resize_image(
                context.user_data["resize_image"], size_text, chat_id
            )

            # Send resized image
            with open(resized_path, "rb") as img_file:
                await update.message.reply_document(
                    document=img_file,
                    filename="resized.png",
                    caption="✅ اندازه عکس تغییر کرد!",
                )

            # Cleanup
            os.remove(resized_path)
            del context.user_data["resize_image"]
            clear_state(chat_id)

            await update.message.reply_text(
                "✅ عملیات با موفقیت انجام شد!", reply_markup=get_main_menu_keyboard()
            )

        except Exception as e:
            await update.message.reply_text(
                f"❌ خطا در تغییر اندازه: {str(e)}\n\nفرمت صحیح: 800x600 یا 50%"
            )

        return

    # Handle image upload
    if update.message.photo or (
        update.message.document
        and update.message.document.mime_type.startswith("image/")
    ):
        await update.message.reply_text("⏳ در حال دریافت عکس...")

        try:
            if update.message.photo:
                photo = update.message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
            else:
                file = await context.bot.get_file(update.message.document.file_id)

            image_bytes = await file.download_as_bytearray()
            context.user_data["resize_image"] = image_bytes

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

        try:
            if update.message.photo:
                photo = update.message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
            else:
                file = await context.bot.get_file(update.message.document.file_id)

            image_bytes = await file.download_as_bytearray()

            # Remove background
            output_path = await remove_background(image_bytes, chat_id)

            # Send result
            with open(output_path, "rb") as img_file:
                await update.message.reply_document(
                    document=img_file,
                    filename="no_background.png",
                    caption="✅ پس‌زمینه عکس حذف شد!",
                )

            # Cleanup
            os.remove(output_path)
            clear_state(chat_id)

            await update.message.reply_text(
                "✅ عملیات با موفقیت انجام شد!", reply_markup=get_main_menu_keyboard()
            )

        except Exception as e:
            await update.message.reply_text(f"❌ خطا در حذف پس‌زمینه: {str(e)}")
            clear_state(chat_id)
    else:
        await update.message.reply_text("❌ لطفاً یک عکس ارسال کنید!")


# Helper functions


async def create_pdf_from_images(images_bytes_list, chat_id):
    """Create PDF from list of image bytes"""

    def _create_pdf():
        images = []
        for img_bytes in images_bytes_list:
            img = Image.open(io.BytesIO(img_bytes))
            if img.mode == "RGBA":
                img = img.convert("RGB")
            images.append(img)

        pdf_path = f"downloads/pdf_{chat_id}.pdf"
        os.makedirs("downloads", exist_ok=True)

        images[0].save(pdf_path, save_all=True, append_images=images[1:])
        return pdf_path

    return await asyncio.to_thread(_create_pdf)


async def convert_image_format(image_bytes, target_format, chat_id):
    """Convert image to target format"""

    def _convert():
        img = Image.open(io.BytesIO(image_bytes))

        # Determine the save format (PIL uses JPEG not JPG)
        save_format = "JPEG" if target_format == "JPG" else target_format

        # Handle transparency for formats that don't support it
        if save_format in ["JPEG", "BMP"] and img.mode in ["RGBA", "LA"]:
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img, mask=img.split()[1])
            img = background

        output_path = f"downloads/converted_{chat_id}.{target_format.lower()}"
        os.makedirs("downloads", exist_ok=True)

        img.save(output_path, format=save_format)
        return output_path

    return await asyncio.to_thread(_convert)


async def resize_image(image_bytes, size_text, chat_id):
    """Resize image based on size text"""

    def _resize():
        img = Image.open(io.BytesIO(image_bytes))

        if "%" in size_text:
            # Percentage resize
            percent = int(size_text.replace("%", ""))
            new_width = int(img.width * percent / 100)
            new_height = int(img.height * percent / 100)
        elif "x" in size_text.lower():
            # Dimension resize
            width, height = size_text.lower().split("x")
            new_width = int(width)
            new_height = int(height)
        else:
            raise ValueError("Invalid size format")

        resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        output_path = f"downloads/resized_{chat_id}.png"
        os.makedirs("downloads", exist_ok=True)

        resized_img.save(output_path)
        return output_path

    return await asyncio.to_thread(_resize)


async def remove_background(image_bytes, chat_id):
    """Remove background from image"""
    if not REMBG_AVAILABLE:
        raise ImportError("rembg library is not installed")

    def _remove_bg():
        input_img = Image.open(io.BytesIO(image_bytes))
        output_img = remove(input_img)

        output_path = f"downloads/no_bg_{chat_id}.png"
        os.makedirs("downloads", exist_ok=True)

        output_img.save(output_path)
        return output_path

    return await asyncio.to_thread(_remove_bg)


# Made with Bob
