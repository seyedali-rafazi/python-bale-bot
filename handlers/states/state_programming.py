# handlers/states/state_programming.py

import os
import re
import uuid
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from services.http_client import get_http_session
from telegram.ext import ContextTypes
from core.state_manager import clear_state
from ddgs import DDGS

# کنترل تعداد درخواست‌های همزمان برای جلوگیری از پر شدن منابع و مسدود شدن IP
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(5)
SEARCH_SEMAPHORE = asyncio.Semaphore(3)


async def background_download(chat_id, bot, download_url, filename, caption):
    temp_filepath = f"temp_{uuid.uuid4().hex}_{filename}"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with DOWNLOAD_SEMAPHORE:
            session = await get_http_session()
            async with session.get(download_url, headers=headers, timeout=120) as response:
                if response.status == 200:
                    # دانلود فایل به صورت تکه‌ای (Chunk) روی هارد به جای پر کردن RAM
                    with open(temp_filepath, "wb") as f:
                        async for chunk in response.content.iter_chunked(
                            1024 * 1024
                        ):  # تکه‌های 1 مگابایتی
                            f.write(chunk)

                        # ارسال مستقیم فایل از روی هارد
                        await bot.send_document(
                            chat_id=chat_id,
                            document=temp_filepath,
                            filename=filename,
                            caption=caption,
                            read_timeout=120,
                            write_timeout=120,
                        )
                    else:
                        await bot.send_message(
                            chat_id,
                            f"❌ خطا در دریافت فایل. کد خطا: {response.status}",
                        )
    except Exception as e:
        await bot.send_message(chat_id, f"❌ خطای غیرمنتظره در دانلود: {e}")
    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        clear_state(chat_id)


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
            download_url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=114.0.0.0&acceptformat=crx2,crx3&x=id%3D{ext_id}%26uc"

            asyncio.create_task(
                background_download(
                    chat_id,
                    context.bot,
                    download_url,
                    f"chrome_{ext_id}.crx",
                    "🌐 افزونه کروم.\nنصب: Developer Mode کروم را روشن کرده و فایل را رها کنید.",
                )
            )
        else:
            await update.message.reply_text(
                "🔍 در حال جستجوی نام افزونه (لطفا کمی صبر کنید)..."
            )
            try:
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

                            asyncio.create_task(
                                background_download(
                                    chat_id,
                                    context.bot,
                                    file_url,
                                    filename,
                                    f"🦊 افزونه فایرفاکس: {addon.get('name', {}).get('en-US', text)}",
                                )
                            )
                        else:
                            await update.message.reply_text("❌ یافت نشد.")
                            clear_state(chat_id)
        except Exception:
            await update.message.reply_text("❌ خطا در ارتباط.")
            clear_state(chat_id)

    elif step == "waiting_prog_vscode":
        parts = text.split(".")
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه است. مثال: `esbenp.prettier-vscode`"
            )
            return

        await update.message.reply_text("⏳ در صف دانلود...")
        publisher, extension_name = parts
        download_url = f"https://{publisher}.gallery.vsassets.io/_apis/public/gallery/publisher/{publisher}/extension/{extension_name}/latest/assetbyname/Microsoft.VisualStudio.Services.VSIXPackage"

        asyncio.create_task(
            background_download(
                chat_id,
                context.bot,
                download_url,
                f"{text}.vsix",
                "💻 افزونه VS Code.\nنصب: از بخش Extensions > Install from VSIX.",
            )
        )


async def handle_chrome_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass  # جلوگیری از کرش در صورت تایم‌اوت شدن کوئری

    data = query.data
    if data.startswith("dlchrome_"):
        ext_id = data.split("_")[1]
        chat_id = query.message.chat_id

        await query.message.reply_text("⏳ دانلود در پس‌زمینه شروع شد...")
        download_url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=114.0.0.0&acceptformat=crx2,crx3&x=id%3D{ext_id}%26uc"

        asyncio.create_task(
            background_download(
                chat_id,
                context.bot,
                download_url,
                f"chrome_{ext_id}.crx",
                "🌐 فایل افزونه کروم.",
            )
        )
