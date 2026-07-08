# handlers/states/state_telegram.py

import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup
from services.http_client import get_http_session
from services.telegram_public import (
    USER_AGENT,
    parse_html_message,
    parse_message_element,
    send_parsed_message,
)
from services import telegram_telethon
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.database import is_vip, get_tg_downloads, increment_tg_downloads, log_upload_success
from core.limits import get_limit

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 10
LATEST_MESSAGE_COUNT = 20
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT)


async def check_tg_limit(update: Update, user_id: str) -> bool:
    vip = await is_vip(user_id)
    max_dl = get_limit("telegram_download", vip)
    current = await get_tg_downloads(user_id)
    if current >= max_dl:
        await update.message.reply_text(
            f"❌ محدودیت روزانه تلگرام شما تمام شده است.\n"
            f"📊 امروز: {current} از {max_dl}\n"
            f"{'🌟 با VIP تا ۱۰ بار در روز' if not vip else ''}"
        )
        return False
    return True


async def fetch_url_async(url: str) -> str:
    timeout = aiohttp.ClientTimeout(total=20)
    session = await get_http_session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with session.get(url, headers=headers, timeout=timeout) as response:
        response.raise_for_status()
        return await response.text()


def _parse_channel_messages_from_html(soup: BeautifulSoup) -> list:
    messages = soup.find_all(
        "div",
        class_=lambda c: c and "tgme_widget_message" in c.split(),
    )
    if not messages:
        messages = soup.select("div.tgme_widget_message_wrap div.tgme_widget_message")
    return messages


async def _send_latest_via_telethon(bot, chat_id: str, channel_id: str) -> bool:
    messages = await telegram_telethon.fetch_channel_messages(
        channel_id, limit=LATEST_MESSAGE_COUNT
    )
    if not messages:
        return False

    any_sent = False
    for msg in reversed(messages):
        if msg and await telegram_telethon.send_message_via_bot(bot, chat_id, msg):
            any_sent = True
    return any_sent


async def _send_latest_via_scrape(bot, chat_id: str, channel_id: str) -> bool:
    channel_id = telegram_telethon.normalize_channel_id(channel_id)
    url = f"https://t.me/s/{channel_id}"
    html_content = await fetch_url_async(url)
    soup = await asyncio.to_thread(BeautifulSoup, html_content, "html.parser")
    messages = _parse_channel_messages_from_html(soup)
    logger.info(
        "HTML scrape @%s: html_len=%s message_divs=%s",
        channel_id,
        len(html_content),
        len(messages),
    )
    latest_messages = messages[-LATEST_MESSAGE_COUNT:]

    if not latest_messages:
        return False

    any_sent = False
    for msg in latest_messages:
        parsed = parse_message_element(msg)
        if await send_parsed_message(bot, chat_id, parsed):
            any_sent = True
    return any_sent


async def handle_telegram_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    user_id = str(update.effective_user.id)

    if not await check_tg_limit(update, user_id):
        set_state(chat_id, "")
        return

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
    success = False

    try:
        async with processing_semaphore:
            if step == "waiting_tg_single":
                link = text.strip()
                try:
                    if await telegram_telethon.telethon_available():
                        try:
                            msg = await telegram_telethon.fetch_single_message(link)
                            if msg:
                                success = (
                                    await telegram_telethon.send_message_via_bot(
                                        bot, chat_id, msg
                                    )
                                )
                        except Exception as te:
                            logger.exception("Telethon single message failed: %s", te)

                    if not success:
                        embed_url = link + ("&" if "?" in link else "?") + "embed=1"
                        html_content = await fetch_url_async(embed_url)
                        soup = await asyncio.to_thread(
                            BeautifulSoup, html_content, "html.parser"
                        )
                        parsed = parse_html_message(soup)
                        success = await send_parsed_message(bot, chat_id, parsed)

                    if not success:
                        await update.message.reply_text(
                            "❌ محتوایی در این لینک یافت نشد، یا فایل‌ها از وب قابل دریافت نیستند."
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
                channel_id = telegram_telethon.normalize_channel_id(text)
                try:
                    telethon_ok = await telegram_telethon.telethon_available()
                    telethon_err = None
                    if telethon_ok:
                        try:
                            success = await _send_latest_via_telethon(
                                bot, chat_id, channel_id
                            )
                        except Exception as te:
                            logger.exception("Telethon channel fetch failed")
                            telethon_err = telegram_telethon.telethon_user_error(te)

                    if not success:
                        try:
                            success = await _send_latest_via_scrape(
                                bot, chat_id, channel_id
                            )
                        except aiohttp.ClientError as e:
                            print(f"Network Error: {e}")
                            await update.message.reply_text(
                                "❌ خطا در دریافت شبکه! ممکن است آیدی معتبر نباشد."
                            )

                    if not success:
                        hint = ""
                        if not telethon_ok:
                            hint = (
                                "\n\n💡 Telethon متصل نیست — API_ID/API_HASH و لاگین "
                                "session (فایل ai_session) را در سرور بررسی کنید."
                            )
                        elif telethon_err:
                            hint = f"\n\n{telethon_err}"
                        await update.message.reply_text(
                            "❌ پیامی یافت نشد! مطمئن شوید آیدی صحیح است و کانال عمومی می‌باشد."
                            + hint
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

            if success:
                await increment_tg_downloads(user_id)
                await log_upload_success("telegram", user_id)

    except Exception as general_err:
        print(f"Queue/Processing Error: {general_err}")
        await update.message.reply_text("❌ خطای سیستمی رخ داد. لطفاً مجدداً تلاش کنید.")

    finally:
        set_state(chat_id, "")
