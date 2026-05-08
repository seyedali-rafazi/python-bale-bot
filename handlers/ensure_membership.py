import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
load_dotenv()

CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_URL = os.getenv("CHANNEL_URL")


async def ensure_membership(update, context) -> bool:
    user = update.effective_user
    if not user:
        return True

    if not CHANNEL_ID:
        return True

    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user.id)
        if member.status in ["member", "administrator", "creator"]:
            return True

    except Exception as e:
        print(f"[membership] {type(e).__name__}: {e}")
        # اگر API مشکل داشت، فعلاً قفل را باز بگذار
        return True

    keyboard = [[InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_URL)]]

    if update.callback_query:
        await update.callback_query.answer(
            "ابتدا باید عضو کانال شوید.", show_alert=True
        )
        try:
            await update.callback_query.message.reply_text(
                "🛑 برای استفاده از این بخش، ابتدا در کانال عضو شوید.\n"
                "بعد از عضویت دوباره امتحان کنید.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            "🛑 برای استفاده از این بخش، ابتدا در کانال عضو شوید.\n"
            "بعد از عضویت دوباره امتحان کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    return False
