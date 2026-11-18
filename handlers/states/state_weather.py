import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.weather import get_weather_forecast
from core.state_manager import clear_state
from core.database import log_upload_success
from handlers.utils import safe_edit_or_reply


async def handle_weather_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_weather_city":
        wait_msg = None
        try:
            wait_msg = await update.message.reply_text(f"⏳ در حال دریافت آب و هوای {text}...")

            # فراخوانی مستقیم تابع ناهمگام آب و هوا
            result = await get_weather_forecast(text)
            await wait_msg.edit_text(result, parse_mode="Markdown")
            if not result.startswith("❌"):
                await log_upload_success("weather", chat_id)
        except Exception as e:
            print(f"Weather State Error: {e}")
            await safe_edit_or_reply(wait_msg or update.message, "❌ خطایی در پردازش آب و هوا رخ داد.")
        finally:
            clear_state(chat_id)
