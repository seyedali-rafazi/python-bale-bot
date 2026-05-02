# handlers/error_handler.py

import traceback
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import get_state

# می‌توانید آیدی کانال مخصوص ارورها را در .env قرار دهید
# یا مستقیماً از ADMIN_ID استفاده کنید
ERROR_CHANNEL_ID = "@digierrorsection"


async def global_error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """مدیریت خطاهای ربات و ارسال جزئیات به ادمین"""

    # دریافت لاگ کامل خطا
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = "".join(tb_list)

    # استخراج اطلاعات کاربر و اکشن او
    user_info = "نامشخص"
    chat_id = "نامشخص"
    user_action = "نامشخص (شاید آپدیت داخلی بوده)"
    user_state = "ندارد"

    if isinstance(update, Update):
        if update.effective_user:
            user_info = f"{update.effective_user.first_name} (ID: <code>{update.effective_user.id}</code>)"
            chat_id = (
                str(update.effective_chat.id) if update.effective_chat else "نامشخص"
            )
            user_state = get_state(chat_id)

        if update.effective_message:
            user_action = update.effective_message.text or "یک فایل/عکس ارسال کرد"
        elif update.callback_query:
            user_action = f"دکمه شیشه‌ای (کال‌بک): {update.callback_query.data}"

    # کوتاه کردن لاگ در صورتی که خیلی طولانی باشد (محدودیت تلگرام)
    short_error = str(context.error)

    error_message = (
        f"⚠️ <b>یک خطای جدید در ربات رخ داد!</b>\n\n"
        f"👤 <b>کاربر:</b> {user_info}\n"
        f"💬 <b>اقدام کاربر (متنی که فرستاده/دکمه‌ای که زده):</b>\n{user_action}\n\n"
        f"🔄 <b>وضعیت استیت (State) کاربر:</b> {user_state}\n\n"
        f"❌ <b>نوع خطا:</b> {type(context.error).__name__}\n"
        f"📄 <b>متن خطا:</b> {short_error}\n"
    )

    print(f"Exception while handling an update: {context.error}")

    if ERROR_CHANNEL_ID:
        try:
            await context.bot.send_message(
                chat_id=ERROR_CHANNEL_ID, text=error_message, parse_mode="HTML"
            )
            # اگر نیاز دارید لاگ کامل خطا (Traceback) هم فرستاده شود، خط زیر را از کامنت خارج کنید:
            await context.bot.send_message(
                chat_id=ERROR_CHANNEL_ID,
                text=f"<pre>{tb_string[-3900:]}</pre>",
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"خطا در ارسال پیام ارور به کانال/ادمین: {e}")


async def send_custom_error_to_admin(
    context: ContextTypes.DEFAULT_TYPE, custom_message: str
):
    """ارسال خطاهای گرفته شده توسط try..except به ادمین"""
    if ERROR_CHANNEL_ID:
        try:
            await context.bot.send_message(
                chat_id=ERROR_CHANNEL_ID,
                text=f"⚠️ <b>خطای داخلی ربات (Catch شده):</b>\n\n{custom_message}",
                parse_mode="HTML",
            )
        except Exception:
            pass

