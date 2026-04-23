import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.weather import get_weather_forecast


async def handle_weather_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_weather_city":
        await update.message.reply_text(f"⏳ در حال دریافت آب و هوای {text}...")

        # فراخوانی سرویس آب و هوا
        result = await asyncio.to_thread(get_weather_forecast, text)
        await update.message.reply_text(result)
