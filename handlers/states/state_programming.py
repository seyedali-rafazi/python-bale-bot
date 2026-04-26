import re
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import clear_state
from duckduckgo_search import AsyncDDGS


async def background_download(chat_id, bot, download_url, filename, caption):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status == 200:
                    file_bytes = await response.read()
                    await bot.send_document(
                        chat_id=chat_id,
                        document=file_bytes,
                        filename=filename,
                        caption=caption,
                    )
                else:
                    await bot.send_message(
                        chat_id, "❌ خطا در دریافت فایل از سرور اصلی."
                    )
    except Exception as e:
        await bot.send_message(chat_id, f"❌ خطای غیرمنتظره در دانلود: {e}")
    finally:
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

            await update.message.reply_text(
                "⏳ درخواست شما در صف دانلود (پس‌زمینه) قرار گرفت..."
            )
            download_url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=49.0&acceptformat=crx3&x=id%3D{ext_id}%26installsource%3Dondemand%26uc"

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
            await update.message.reply_text("🔍 در حال جستجوی نام افزونه...")
            try:
                query = f"site:chromewebstore.google.com {text}"
                results = await AsyncDDGS().atext(query, max_results=3)

                if not results:
                    await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
                else:
                    keyboard = []
                    response_msg = "✅ **نتایج یافت شده:**\n\n"

                    for idx, res in enumerate(results, 1):
                        title = res.get("title", "بدون عنوان").replace(
                            " - Chrome Web Store", ""
                        )
                        link = res.get("href", "")
                        ext_id_match = re.search(r"([a-z]{32})", link)

                        if ext_id_match:
                            ext_id = ext_id_match.group(1)
                            response_msg += f"{idx}. **{title}**\n"
                            keyboard.append(
                                [
                                    InlineKeyboardButton(
                                        f"📥 دانلود گزینه {idx}",
                                        callback_data=f"dlchrome_{ext_id}",
                                    )
                                ]
                            )

                    if keyboard:
                        await update.message.reply_text(
                            response_msg,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode="Markdown",
                        )
                    else:
                        await update.message.reply_text("❌ شناسه‌ای یافت نشد.")
            except Exception:
                await update.message.reply_text("❌ خطا در جستجو.")

    elif step == "waiting_prog_firefox":
        await update.message.reply_text("⏳ در صف دانلود...")
        search_url = f"https://addons.mozilla.org/api/v5/addons/search/?q={text}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url) as response:
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


# پردازش دکمه‌های شیشه‌ای کروم
async def handle_chrome_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("dlchrome_"):
        ext_id = data.split("_")[1]
        chat_id = query.message.chat_id

        await query.message.reply_text("⏳ دانلود در پس‌زمینه شروع شد...")
        download_url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=49.0&acceptformat=crx3&x=id%3D{ext_id}%26installsource%3Dondemand%26uc"

        asyncio.create_task(
            background_download(
                chat_id,
                context.bot,
                download_url,
                f"chrome_{ext_id}.crx",
                "🌐 فایل افزونه کروم.",
            )
        )
