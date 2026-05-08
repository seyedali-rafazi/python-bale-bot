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
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user.id,
        )

        if member.status in ["member", "administrator", "creator", "owner"]:
            return True
        else:
            is_member = False

    except Exception as e:
        print(f"[membership] {type(e).__name__}: {e}")
        is_member = False

    if is_member:
        return True

    keyboard = [[InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_URL)]]
    text = (
        "🛑 برای استفاده از این بخش، ابتدا در کانال عضو شوید.\n"
        "بعد از عضویت دوباره امتحان کنید."
    )

    if update.callback_query:
        try:
            await update.callback_query.answer(
                "ابتدا باید عضو کانال شوید.",
                show_alert=True,
            )
        except Exception:
            pass

        try:
            await update.callback_query.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            print(f"[membership reply callback] {type(e).__name__}: {e}")

    elif update.message:
        try:
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            print(f"[membership reply message] {type(e).__name__}: {e}")

    return False
