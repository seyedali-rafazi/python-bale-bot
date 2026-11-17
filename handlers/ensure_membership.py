import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

from services.cache_service import cache_get, cache_set

load_dotenv()

CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_URL = os.getenv("CHANNEL_URL")
MEMBERSHIP_CACHE_TTL_SEC = max(30, int(os.getenv("MEMBERSHIP_CACHE_TTL_SEC", "300")))

_VALID_MEMBER_STATUSES = frozenset({"member", "administrator", "creator", "owner"})


async def is_user_channel_member(bot, user_id: str | int) -> bool:
    """Check channel membership with positive Redis/memory caching to cut Bale API load."""
    if not CHANNEL_ID:
        return True

    uid = str(user_id)
    cache_key = f"channel_member:{CHANNEL_ID}:{uid}"
    cached = await cache_get(cache_key)
    if cached is not None and bool(cached):
        return True

    try:
        member = await bot.get_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user_id,
        )
        if getattr(member, "status", None) in _VALID_MEMBER_STATUSES:
            await cache_set(cache_key, 1, ttl_sec=MEMBERSHIP_CACHE_TTL_SEC)
            return True
    except Exception as e:
        print(f"[membership] {type(e).__name__}: {e}")

    return False


async def ensure_membership(update, context) -> bool:
    user = update.effective_user
    if not user:
        return True

    if await is_user_channel_member(context.bot, user.id):
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
