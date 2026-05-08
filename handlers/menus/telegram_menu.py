from core.state_manager import set_state
from core.keyboards import get_telegram_menu_keyboard
from handlers.ensure_membership import ensure_membership


async def btn_telegram_menu(update, context):
    if not await ensure_membership(update, context):
        return
    await update.message.reply_text(
        "به منوی تلگرام خوش آمدید. یک گزینه را انتخاب کنید:",
        reply_markup=get_telegram_menu_keyboard(),
    )


async def btn_tg_single_req(update, context):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tg_single")
    await update.message.reply_text(
        "لطفاً لینک پیام تلگرام را بفرستید (مثال: https://t.me/channel_id/1234):"
    )


async def btn_tg_latest_req(update, context):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tg_latest")
    await update.message.reply_text(
        "لطفاً آیدی کانال عمومی تلگرام را بفرستید (مثال: @varzesh3 یا varzesh3):"
    )
