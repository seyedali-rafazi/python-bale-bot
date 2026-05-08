from core.state_manager import set_state
from handlers.ensure_membership import ensure_membership


async def btn_pinterest_req(update, context):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_pinterest")
    await update.message.reply_text(
        "📌 کلمه یا موضوعی که می‌خواهید عکس آن را ببینید بفرستید:"
    )
