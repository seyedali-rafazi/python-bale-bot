import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.database import get_gh_downloads, increment_gh_downloads, is_vip
from core.state_manager import clear_state
import uuid
import os


async def handle_github_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):

    user_id = update.effective_user.id
    vip_status = is_vip(str(user_id))
    max_dl = 10 if vip_status else 4

    if get_gh_downloads(str(user_id)) >= max_dl:
        await update.message.reply_text(
            "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
        )
        clear_state(chat_id)
        return

    if step == "waiting_gh_dl":
        # فرمت ورودی باید username/repo باشد
        repo_path = text.replace("https://github.com/", "").strip()
        await process_github_download(update, context, chat_id, repo_path, str(user_id))

    elif step == "waiting_gh_user":
        # دریافت ریپوهای یک کاربر
        await update.message.reply_text("⏳ در حال دریافت اطلاعات کاربر...")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.github.com/users/{text}/repos?sort=updated&per_page=10"
            ) as resp:
                if resp.status == 200:
                    repos = await resp.json()
                    msg = f"📂 ۱۰ ریپازیتوری آخر {text}:\n\n"
                    keyboard = []
                    for i, repo in enumerate(repos):
                        msg += f"{i + 1}. {repo['name']}\n"
                        keyboard.append(
                            [
                                InlineKeyboardButton(
                                    f"📥 دانلود {repo['name']}",
                                    callback_data=f"ghdl_{repo['full_name']}",
                                )
                            ]
                        )

                    await update.message.reply_text(
                        msg, reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await update.message.reply_text("❌ کاربر یافت نشد.")

    elif step == "waiting_gh_search":
        await update.message.reply_text("⏳ در حال جستجو در گیت‌هاب...")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.github.com/search/repositories?q={text}&per_page=10"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    repos = data.get("items", [])
                    if not repos:
                        await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
                        return

                    msg = f"🔍 ۱۰ نتیجه برتر برای «{text}»:\n\n"
                    keyboard = []
                    for i, repo in enumerate(repos):
                        msg += f"{i + 1}. {repo['full_name']} (⭐ {repo['stargazers_count']})\n"
                        keyboard.append(
                            [
                                InlineKeyboardButton(
                                    f"📥 دانلود {repo['name']}",
                                    callback_data=f"ghdl_{repo['full_name']}",
                                )
                            ]
                        )

                    await update.message.reply_text(
                        msg, reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await update.message.reply_text("❌ خطا در ارتباط با گیت‌هاب.")


async def process_github_download(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id, repo_path, user_id
):
    await update.message.reply_text("⏳ در حال آماده‌سازی فایل و گرفتن اسکرین‌شات...")

    zip_url = f"https://api.github.com/repos/{repo_path}/zipball"
    screenshot_url = f"https://image.thum.io/get/fullpage/https://github.com/{repo_path}"  # API رایگان اسکرین‌شات (میتوانید تغییر دهید)

    file_name = f"{repo_path.replace('/', '_')}.zip"
    temp_path = f"temp_{uuid.uuid4().hex}_{file_name}"

    try:
        async with aiohttp.ClientSession() as session:
            # ارسال اسکرین شات
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=screenshot_url,
                caption=f"📸 نمای کلی از 리پازیتوری: {repo_path}",
            )

            # دانلود ریپو
            async with session.get(zip_url) as resp:
                if resp.status == 200:
                    with open(temp_path, "wb") as f:
                        f.write(await resp.read())

                    await context.bot.send_document(
                        chat_id=chat_id, document=temp_path, filename=file_name
                    )
                    increment_gh_downloads(user_id)
                else:
                    await context.bot.send_message(
                        chat_id,
                        "❌ خطایی در دانلود ریپازیتوری رخ داد (ممکن است شاخه اصلی main نباشد).",
                    )
    except Exception as e:
        await context.bot.send_message(chat_id, "❌ خطا در پردازش.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        clear_state(chat_id)


async def github_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    user_id = str(query.from_user.id)

    if data.startswith("ghdl_"):
        repo_path = data.split("ghdl_")[1]
        vip_status = is_vip(user_id)
        max_dl = 10 if vip_status else 4
        if get_gh_downloads(user_id) >= max_dl:
            await query.message.reply_text(
                "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
            )
            return

        await process_github_download(query, context, chat_id, repo_path, user_id)
