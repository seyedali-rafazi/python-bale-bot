# services/ai_abstract.py

import os
import asyncio
import aiohttp
from telethon import TelegramClient
from dotenv import load_dotenv
from .research import clean_doi

load_dotenv()

CHATGPT_BOT_USERNAME = os.getenv("CHATGPT_BOT_USERNAME")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("AI_SESSION_NAME")

telethon_client: TelegramClient | None = None
chatgpt_lock = asyncio.Lock()


async def startup_telethon_client():
    global telethon_client
    if not all([API_ID, API_HASH, SESSION_NAME]):
        return
    telethon_client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    try:
        await telethon_client.start()
    except Exception as e:
        print(f"❌ AI Client Error: {e}")
        telethon_client = None


async def shutdown_telethon_client():
    global telethon_client
    if telethon_client and telethon_client.is_connected():
        await telethon_client.disconnect()


async def get_abstract_from_openalex(doi_input: str) -> str | None:
    doi_clean = clean_doi(doi_input)
    url = f"https://api.openalex.org/works/https://doi.org/{doi_clean}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    item = await response.json()
                    idx = item.get("abstract_inverted_index", {})
                    if not idx:
                        return None
                    words = sorted(
                        (
                            (pos, word)
                            for word, positions in idx.items()
                            for pos in positions
                        ),
                        key=lambda x: x[0],
                    )
                    return " ".join([w[1] for w in words])
    except:
        pass
    return None


async def analyze_abstract_with_ai(abstract_text: str) -> str:
    if not telethon_client or not telethon_client.is_connected():
        return "⚠️ سرویس موقتا در دسترس نیست."

    # قفل کردن برای پردازش نفر به نفر
    async with chatgpt_lock:
        try:
            prompt = f"لطفا این چکیده علمی را تحلیل کن و فقط متن تحلیل را بده بدون هیچ سوال اضافه‌ای:\n\n{abstract_text}"

            # ارسال پیام و دریافت آیدی آن
            sent_msg = await telethon_client.send_message(CHATGPT_BOT_USERNAME, prompt)

            for _ in range(25):
                await asyncio.sleep(5)
                # فقط پیام‌هایی که بعد از پیام ما ارسال شده‌اند را می‌گیرد
                messages = await telethon_client.get_messages(
                    CHATGPT_BOT_USERNAME, min_id=sent_msg.id
                )

                for msg in messages:
                    if (
                        msg.text
                        and not msg.out
                        and not msg.sticker
                        and len(msg.text.strip()) > 20
                    ):
                        return msg.text

            return "❌ زمان انتظار پایان یافت."
        except Exception as e:
            return "❌ خطا در برقراری ارتباط."
