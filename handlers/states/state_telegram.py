# handlers/states/state_telegram.py

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from services.http_client import get_http_session
from services.telegram_public import (
    parse_html_message,
    parse_message_element,
    send_parsed_message,
)
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state

# --- تنظیمات پردازش ---
MAX_CONCURRENT = 10
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT)


async def fetch_url_async(url: str) -> str:
    """دریافت محتوای صفحه به صورت کاملاً غیرهمگام بدون درگیر کردن Thread"""
    timeout = aiohttp.ClientTimeout(total=15)
    session = await get_http_session()
    async with session.get(url, timeout=timeout) as response:
        response.raise_for_status()
        return await response.text()


async def handle_telegram_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    waiters = (
        len(processing_semaphore._waiters)
        if hasattr(processing_semaphore, "_waiters") and processing_semaphore._waiters
        else 0
    )

    if processing_semaphore.locked():
        await update.message.reply_text(
            f"⏳ ربات در حال حاضر مشغول است. شما در صف قرار گرفتید (نفر {waiters + 1} در صف). لطفاً صبور باشید..."
        )
    else:
        await update.message.reply_text("⏳ در حال دریافت اطلاعات از تلگرام...")

    bot = context.bot

    try:
        async with processing_semaphore:
            if step == "waiting_tg_single":
                link = text.strip()
                try:
                    embed_url = link + ("&" if "?" in link else "?") + "embed=1"
                    html_content = await fetch_url_async(embed_url)
                    soup = await asyncio.to_thread(
                        BeautifulSoup, html_content, "html.parser"
                    )
                    parsed = parse_html_message(soup)
                    sent = await send_parsed_message(bot, chat_id, parsed)
                    if not sent:
                        await update.message.reply_text(
                            "❌ محتوایی در این لینک یافت نشد، یا فایل‌ها از وب قابل دریافت نیستند "
                            "(مثلاً سند بدون لینک مستقیم). لینک را در اپ تلگرام باز کنید."
                        )

                except asyncio.TimeoutError:
                    await update.message.reply_text(
                        "❌ ارتباط با سرور زمان‌بر شد. لطفاً دوباره تلاش کنید."
                    )
                except aiohttp.ClientError as e:
                    print(f"Network Error: {e}")
                    await update.message.reply_text(
                        "❌ خطا در دریافت شبکه! ممکن است لینک معتبر نباشد."
                    )
                except Exception as e:
                    print(f"Telegram Scraping Error: {e}")
                    await update.message.reply_text(
                        "❌ خطا در دریافت! محتوا خصوصی است یا حذف شده است."
                    )

            elif step == "waiting_tg_latest":
                channel_id = text.strip().replace("@", "").split("/")[-1]
                try:
                    url = f"https://t.me/s/{channel_id}"
                    html_content = await fetch_url_async(url)
                    soup = await asyncio.to_thread(
                        BeautifulSoup, html_content, "html.parser"
                    )
                    messages = soup.find_all("div", class_="tgme_widget_message")
                    latest_messages = messages[-5:]

                    if not latest_messages:
                        await update.message.reply_text(
                            "❌ پیامی یافت نشد! مطمئن شوید آیدی صحیح است و کانال عمومی می‌باشد."
                        )
                    else:
                        any_sent = False
                        for msg in latest_messages:
                            parsed = parse_message_element(msg)
                            try:
                                if await send_parsed_message(bot, chat_id, parsed):
                                    any_sent = True
                            except Exception as send_err:
                                print(f"Error sending media: {send_err}")
                                if parsed.text:
                                    await bot.send_message(
                                        chat_id=chat_id, text=parsed.text
                                    )
                                    any_sent = True
                        if not any_sent:
                            await update.message.reply_text(
                                "❌ در پیام‌های اخیر، محتوای قابل ارسال (زیر ۲۰ مگابایت) یافت نشد."
                            )

                except asyncio.TimeoutError:
                    await update.message.reply_text(
                        "❌ ارتباط با سرور تلگرام قطع شد. لطفاً بعدا تلاش کنید."
                    )
                except Exception as e:
                    print(f"Telegram Latest Error: {e}")
                    await update.message.reply_text(
                        "❌ خطا در خواندن کانال! ممکن است آیدی اشتباه باشد."
                    )

    except Exception as general_err:
        print(f"Queue/Processing Error: {general_err}")
        await update.message.reply_text("❌ خطای سیستمی رخ داد. لطفاً مجدداً تلاش کنید.")

    finally:
        set_state(chat_id, "")
