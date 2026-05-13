# services/ai.py

import os
import io
import urllib.parse
import asyncio
import aiohttp

from dotenv import load_dotenv
from gtts import gTTS
from telethon import TelegramClient
from telethon.errors import FloodWaitError

from services.http_client import get_http_session

load_dotenv()

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")

CHATGPT_BOT_USERNAME = os.getenv("CHATGPT_BOT_USERNAME")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")

SESSION_NAME = os.getenv("AI_SESSION_NAME", "SESSION_NAME")

# =========================
# GLOBAL TELETHON CLIENT
# =========================

client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH,
)

client_started = False

# حداکثر همزمانی
chatbot_semaphore = asyncio.Semaphore(20)


async def init_ai_client():
    global client_started

    if not client_started:
        await client.connect()

        if not await client.is_user_authorized():
            raise Exception("Telethon account is not authorized")

        client_started = True

        print("✅ Telethon connected")


async def ask_chatbot(text: str):

    await init_ai_client()

    async with chatbot_semaphore:
        try:
            prompt = (
                "این درخواست مستقل است.\n"
                "از تاریخچه استفاده نکن.\n"
                "فقط جواب بده:\n\n"
                f"{text}"
            )

            # timeout برای send
            await asyncio.wait_for(
                client.send_message(
                    CHATGPT_BOT_USERNAME,
                    prompt,
                ),
                timeout=15,
            )

            last_text = ""
            stable_count = 0

            async def wait_response():

                nonlocal last_text
                nonlocal stable_count

                for _ in range(30):
                    await asyncio.sleep(2)

                    messages = await client.get_messages(
                        CHATGPT_BOT_USERNAME,
                        limit=3,
                    )

                    if not messages:
                        continue

                    for msg in messages:
                        if msg.text and not msg.out and not msg.sticker:
                            current_text = msg.text.strip()

                            if len(current_text) < 5:
                                continue

                            if current_text == last_text:
                                stable_count += 1
                            else:
                                stable_count = 0
                                last_text = current_text

                            if stable_count >= 1:
                                return current_text

                return None

            result = await asyncio.wait_for(
                wait_response(),
                timeout=60,
            )

            if result:
                return result

            return "❌ ربات هوش مصنوعی پاسخ نداد."

        except asyncio.TimeoutError:
            return "⏳ سرور AI timeout شد."

        except FloodWaitError as e:
            return f"⛔ محدودیت تلگرام. {e.seconds} ثانیه بعد تلاش کنید."

        except Exception as e:
            print(f"AI ERROR: {e}")
            return "❌ خطا در ارتباط با AI."
