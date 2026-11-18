# handlers/states/state_programming.py

import os
import re
import uuid
import asyncio

try:
    from duckduckgo_search import DDGS
except ImportError:
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


from core.state_manager import clear_state
from core.task_utils import remove_file_async, stream_aiohttp_to_file, track_task
from services.http_client import get_http_session

# کنترل تعداد درخواست‌های همزمان برای جلوگیری از پر شدن منابع و مسدود شدن IP
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(5)
SEARCH_SEMAPHORE = asyncio.Semaphore(3)
_PROG_TEMP_DIR = os.path.join("downloads", "programming")


async def background_download(chat_id, bot, download_url, filename, caption):
    chat_id_str = str(chat_id)
    safe_name = os.path.basename(filename or "download.bin")
    temp_filepath = os.path.join(_PROG_TEMP_DIR, f"temp_{uuid.uuid4().hex}_{safe_name}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with DOWNLOAD_SEMAPHORE:
            session = await get_http_session()
            async with session.get(
                download_url, headers=headers, timeout=120
            ) as response:
                if response.status == 200:
                    await stream_aiohttp_to_file(
                        response, temp_filepath, chunk_size=1024 * 1024
                    )

                    # ارسال مستقیم فایل از روی هارد
                    await bot.send_document(
                        chat_id=chat_id_str,
                        document=temp_filepath,
                        filename=safe_name,
                        caption=caption,
                        read_timeout=120,
                        write_timeout=120,
                    )
                else:
                    await bot.send_message(
                        chat_id_str,
                        f"❌ خطا در دریافت فایل. کد خطا: {response.status}",
                    )
    except Exception as e:
        await bot.send_message(chat_id_str, f"❌ خطای غیرمنتظره در دانلود: {e}")
    finally:
        await remove_file_async(temp_filepath)
        clear_state(chat_id_str)


async def handle_programming_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_prog_chrome":
        is_url = (
            "chromewebstore.google.com" in text or "chrome.google.com/webstore" in text
        )
        is_id = len(text) == 32 and text.isalpha()

        if is_url or is_id:
            ext_id = text if is_id else text.split("/")[-1].split("?")[0]
            if len(ext_id) != 32:
                await update.message.reply_text("❌ شناسه استخراج شده نامعتبر است.")
                return

            await update.message.reply_text("⏳ درخواست شما در صف دانلود قرار گرفت...")
            download_url = (
                "https://clients2.google.com/service/update2/crx"
                f"?response=redirect&prodversion=114.0.0.0&acceptformat=crx2,crx3&x=id%3D{ext_id}%26uc"
            )

            track_task(
                background_download(
                    chat_id,
                    context.bot,
                    download_url,
                    f"chrome_{ext_id}.crx",
                    "🌐 افزونه کروم.\nنصب: Developer Mode کروم را روشن کرده و فایل را رها کنید.",
                ),
                name=f"prog_chrome_{chat_id}",
            )
        else:
            await update.message.reply_text(
                "🔍 در حال جستجوی نام افزونه (لطفا کمی صبر کنید)..."
            )
            try:
                if DDGS is None:
                    await update.message.reply_text("❌ سرویس جستجوی افزونه در دسترس نیست.")
                    return

                query = f"chrome web store extension {text}"

                def perform_search(q):
                    with DDGS() as ddgs:
                        return list(ddgs.text(q, max_results=5))

                # استفاده از قفل برای جلوگیری از اسپم شدن DuckDuckGo
                async with SEARCH_SEMAPHORE:
                    results = await asyncio.to_thread(perform_search, query)

                if not results:
                    await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
                else:
                    keyboard = []
                    response_msg = "✅ **نتایج یافت شده:**\n\n"
                    count = 1

                    for res in results:
                        link = res.get("href", "")
                        if (
                            "chromewebstore.google.com" in link
                            or "chrome.google.com/webstore" in link
                        ):
                            title = res.get("title", "بدون عنوان").split("-")[0].strip()
                            ext_id_match = re.search(r"([a-z]{32})", link)

                            if ext_id_match and count <= 3:
                                ext_id = ext_id_match.group(1)
                                response_msg += f"{count}. **{title}**\n"
                                keyboard.append(
                                    [
                                        InlineKeyboardButton(
                                            f"📥 دانلود گزینه {count}",
                                            callback_data=f"dlchrome_{ext_id}",
                                        )
                                    ]
                                )
                                count += 1

                    if keyboard:
                        await update.message.reply_text(
                            response_msg,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode="Markdown",
                        )
                    else:
                        await update.message.reply_text(
                            "❌ شناسه‌ای یافت نشد. لطفاً لینک دقیق را ارسال کنید."
                        )
            except Exception as e:
                await update.message.reply_text(f"❌ خطا در جستجو: {e}")

    elif step == "waiting_prog_firefox":
        await update.message.reply_text("⏳ در صف دانلود...")
        search_url = f"https://addons.mozilla.org/api/v5/addons/search/?q={text}"
        try:
            session = await get_http_session()
            async with session.get(search_url, timeout=60) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("results"):
                        addon = data["results"][0]
                        file_url = addon["current_version"]["file"]["url"]
                        filename = f"{addon['slug']}.xpi"

                        track_task(
                            background_download(
                                chat_id,
                                context.bot,
                                file_url,
                                filename,
                                f"🦊 افزونه فایرفاکس: {addon.get('name', {}).get('en-US', text)}",
                            ),
                            name=f"prog_firefox_{chat_id}",
                        )
                    else:
                        await update.message.reply_text("❌ یافت نشد.")
                        clear_state(chat_id)
                else:
                    await update.message.reply_text(
                        f"❌ خطا در دریافت اطلاعات. کد: {response.status}"
                    )
                    clear_state(chat_id)
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ارتباط: {e}")
            clear_state(chat_id)

    elif step == "waiting_prog_vscode":
        parts = text.split(".")
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه است. مثال: `esbenp.prettier-vscode`",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text("⏳ در صف دانلود...")
        publisher, extension_name = parts
        download_url = (
            f"https://{publisher}.gallery.vsassets.io/_apis/public/gallery/"
            f"publisher/{publisher}/extension/{extension_name}/latest/assetbyname/"
            "Microsoft.VisualStudio.Services.VSIXPackage"
        )

        track_task(
            background_download(
                chat_id,
                context.bot,
                download_url,
                f"{text}.vsix",
                "💻 افزونه VS Code.\nنصب: از بخش Extensions > Install from VSIX.",
            ),
            name=f"prog_vscode_{chat_id}",
        )


async def handle_chrome_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass  # جلوگیری از کرش در صورت تایم‌اوت شدن کوئری

    data = query.data
    if data.startswith("dlchrome_"):
        ext_id = data.split("_", 1)[1]
        chat_id = str(query.message.chat_id)

        await query.message.reply_text("⏳ دانلود در پس‌زمینه شروع شد...")
        download_url = (
            "https://clients2.google.com/service/update2/crx"
            f"?response=redirect&prodversion=114.0.0.0&acceptformat=crx2,crx3&x=id%3D{ext_id}%26uc"
        )

        track_task(
            background_download(
                chat_id,
                context.bot,
                download_url,
                f"chrome_{ext_id}.crx",
                "🌐 فایل افزونه کروم.",
            ),
            name=f"prog_chrome_cb_{chat_id}",
        )
