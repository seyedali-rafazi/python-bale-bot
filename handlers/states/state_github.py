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
    await context.bot.send_message(
        chat_id, "⏳ در حال آماده‌سازی فایل و گرفتن اسکرین‌شات..."
    )

    # استفاده از لینک دانلود مستقیم وب به جای API برای جلوگیری از دریافت فایل‌های ناقص و خطای 403
    zip_url = f"https://github.com/{repo_path}/archive/HEAD.zip"
    screenshot_url = (
        f"https://image.thum.io/get/fullpage/https://github.com/{repo_path}"
    )

    file_name = f"{repo_path.replace('/', '_')}.zip"
    import uuid, os

    temp_path = f"temp_{uuid.uuid4().hex}_{file_name}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            # ارسال اسکرین شات
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=screenshot_url,
                    caption=f"📸 نمای کلی از ریپازیتوری: {repo_path}",
                )
            except:
                pass

            # دانلود ریپو
            async with session.get(
                zip_url, headers=headers, allow_redirects=True
            ) as resp:
                if resp.status == 200:
                    with open(temp_path, "wb") as f:
                        f.write(await resp.read())

                    file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)

                    # اگر فایل خیلی کوچک باشد (کمتر از 1 کیلوبایت)، احتمالاً فایل معتبری نیست
                    if file_size_mb < 0.001:
                        await context.bot.send_message(
                            chat_id,
                            "❌ فایل دریافتی از گیت‌هاب نامعتبر است (احتمالاً ریپازیتوری وجود ندارد یا پرایوت است).",
                        )
                    elif file_size_mb > 49.5:
                        await context.bot.send_message(
                            chat_id,
                            f"❌ حجم این ریپازیتوری ({file_size_mb:.1f} مگابایت) بیشتر از سقف مجاز تلگرام است.",
                        )
                    else:
                        await context.bot.send_document(
                            chat_id=chat_id, document=temp_path, filename=file_name
                        )
                        # فراخوانی تابع افزایش تعداد دانلود کاربر
                        # increment_gh_downloads(user_id)
                else:
                    await context.bot.send_message(
                        chat_id,
                        f"❌ خطایی در دریافت فایل رخ داد. (کد خطا: {resp.status})",
                    )
    except Exception as e:
        await context.bot.send_message(
            chat_id, "❌ خطا در پردازش یا آپلود فایل در تلگرام."
        )
        print(f"GitHub Error: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        # فراخوانی تابع پاکسازی وضعیت کاربر
        # clear_state(chat_id)


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
