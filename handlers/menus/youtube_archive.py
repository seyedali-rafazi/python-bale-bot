# handlers/menus/youtube_archive.py

import json
from urllib.parse import quote

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes

from core.constants import (
    BTN_BACK,
    BTN_YT_MY_CACHE,
    BTN_YT_CACHE_SEARCH_TITLE,
    BTN_YT_CACHE_SEARCH_CHANNEL,
)
from core.keyboards import get_yt_archive_menu_keyboard, get_youtube_menu_keyboard
from core.state_manager import set_state, clear_state
from core.database import (
    count_user_archive,
    get_user_archive_limit,
    get_user_channels_page,
    count_user_channels,
    get_channel_videos_page,
    count_channel_videos,
    get_archive_entry,
    search_archive_by_title,
    search_archive_by_channel,
    can_user_fetch_from_archive,
    increment_archive_fetch,
    increment_yt_video_view,
    CHANNELS_PAGE_SIZE,
    VIDEOS_PAGE_SIZE,
    ARCHIVE_LIMIT_FREE,
    ARCHIVE_LIMIT_VIP,
)
from core.database.vip import is_vip
from handlers.ensure_membership import ensure_membership
from handlers.states.youtube.helpers import send_cached_files


def _channel_callback_data(page: int, index: int) -> str:
    return f"ytarc_ch_{page}_{index}"


def _encode_channel(channel_name: str) -> str:
    return quote(channel_name, safe="")


def _decode_channel(encoded: str) -> str:
    from urllib.parse import unquote

    return unquote(encoded)


async def _send_archive_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    total_global = await count_user_archive()
    limit = await get_user_archive_limit(user_id)
    _, used, _ = await can_user_fetch_from_archive(user_id)
    vip = await is_vip(user_id)

    plan = "Pro" if vip == 1 else "رایگان"
    feature_text = (
        "📚 **کش مشترک ویدیوهای یوتیوب**\n\n"
        "وقتی هر کاربری ویدیویی دانلود کند، برای **همه** در این آرشیو "
        "ذخیره می‌شود و بدون دانلود مجدد قابل دریافت است.\n\n"
        f"🌐 تعداد ویدیو در کش سرور: **{total_global}**\n"
        f"👤 اشتراک شما: **{plan}**\n"
        f"📥 دریافت از آرشیو امروز: **{used}** از **{limit}** "
        f"(رایگان: {ARCHIVE_LIMIT_FREE} | Pro: {ARCHIVE_LIMIT_VIP})\n\n"
        "روی کانال بزنید — ویدیوها از جدید به قدیم مرتب شده‌اند."
    )

    if total_global == 0:
        feature_text += (
            "\n\n📭 هنوز ویدیویی در کش نیست.\n"
            "با اولین دانلود یوتیوب، کش برای همه پر می‌شود."
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "◀️ بازگشت به منوی یوتیوب", callback_data="ytarc_back_yt"
                    )
                ]
            ]
        )
    else:
        channels = await get_user_channels_page(
            offset=0, limit=CHANNELS_PAGE_SIZE
        )
        total_ch = await count_user_channels()
        keyboard = _build_channels_keyboard(
            channels, page=0, total_channels=total_ch
        )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            feature_text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            feature_text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )


def _build_channels_keyboard(
    channels, page: int, total_channels: int
) -> InlineKeyboardMarkup:
    rows = []
    for idx, row in enumerate(channels):
        name = row["channel_name"]
        count = row["video_count"]
        label = f"{name} — {count}"
        if len(label) > 60:
            label = f"{name[:40]}… — {count}"
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=_channel_callback_data(page, idx),
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("◀️ ۵ کانال قبل", callback_data=f"ytarc_chpg_{page - 1}")
        )
    if (page + 1) * CHANNELS_PAGE_SIZE < total_channels:
        nav.append(
            InlineKeyboardButton("۵ کانال بعد ▶️", callback_data=f"ytarc_chpg_{page + 1}")
        )
    nav.append(InlineKeyboardButton("🔄 بروزرسانی", callback_data="ytarc_refresh"))
    if nav:
        rows.append(nav)

    rows.append(
        [InlineKeyboardButton("◀️ بازگشت به منوی یوتیوب", callback_data="ytarc_back_yt")]
    )
    return InlineKeyboardMarkup(rows)


async def btn_yt_my_cache_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return

    chat_id = str(update.effective_chat.id)
    clear_state(chat_id)

    await update.message.reply_text(
        "از دکمه‌های زیر می‌توانید در آرشیو جستجو کنید:",
        reply_markup=get_yt_archive_menu_keyboard(),
    )
    await _send_archive_overview(update, context)


async def btn_yt_cache_search_title_req(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_archive_search_title")
    await update.message.reply_text(
        "عنوان یا بخشی از موضوع ویدیو را بنویسید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_cache_search_channel_req(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_archive_search_channel")
    await update.message.reply_text(
        "نام کانال یا بخشی از آن را بنویسید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def handle_yt_archive_search_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
):
    if step == "waiting_yt_archive_search_title":
        results = await search_archive_by_title(text)
        empty_msg = "نتیجه‌ای برای این عنوان در کش مشترک پیدا نشد."
    else:
        results = await search_archive_by_channel(text)
        empty_msg = "نتیجه‌ای برای این کانال در کش مشترک پیدا نشد."

    if not results:
        await update.message.reply_text(empty_msg)
        return

    keyboard = []
    lines = ["🔍 نتایج جستجو (جدیدترین اول):\n"]
    for row in results[:12]:
        title = row["title"]
        if len(title) > 45:
            title = title[:42] + "…"
        ch = row["channel_name"]
        lines.append(f"• {title}\n  📺 {ch}")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"▶️ {title[:30]}",
                    callback_data=f"ytarc_vid_{row['id']}",
                )
            ]
        )

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def yt_archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = str(query.from_user.id)

    if data == "ytarc_refresh":
        await _send_archive_overview(update, context)
        return

    if data == "ytarc_back_yt":
        await query.answer()
        await query.message.reply_text(
            "📺 منوی یوتیوب:",
            reply_markup=get_youtube_menu_keyboard(),
        )
        return

    if data.startswith("ytarc_chpg_"):
        page = int(data.split("_")[-1])
        offset = page * CHANNELS_PAGE_SIZE
        channels = await get_user_channels_page(
            offset=offset, limit=CHANNELS_PAGE_SIZE
        )
        total_ch = await count_user_channels()
        total_pages = max(1, (total_ch + CHANNELS_PAGE_SIZE - 1) // CHANNELS_PAGE_SIZE)

        if not channels and page > 0:
            await query.answer("صفحه‌ای وجود ندارد.")
            return

        text = (
            f"📚 کانال‌های کش مشترک (صفحه {page + 1} از {total_pages})\n\n"
            "روی کانال بزنید:"
        )
        keyboard = _build_channels_keyboard(
            channels, page=page, total_channels=total_ch
        )
        await query.answer()
        await query.edit_message_text(text, reply_markup=keyboard)
        return

    if data.startswith("ytarc_ch_"):
        parts = data.split("_")
        page = int(parts[2])
        index = int(parts[3])
        offset = page * CHANNELS_PAGE_SIZE
        channels = await get_user_channels_page(
            offset=offset, limit=CHANNELS_PAGE_SIZE
        )
        if index >= len(channels):
            await query.answer("کانال یافت نشد.")
            return
        channel_name = channels[index]["channel_name"]
        context.user_data["ytarc_channel"] = channel_name
        await _show_channel_videos(update, context, channel_name, page=0)
        return

    if data.startswith("ytarc_vidpg_"):
        encoded = data.replace("ytarc_vidpg_", "", 1)
        channel_name, vid_page = encoded.rsplit("_", 1)
        channel_name = _decode_channel(channel_name)
        await _show_channel_videos(
            update, context, channel_name, page=int(vid_page)
        )
        return

    if data.startswith("ytarc_vid_"):
        archive_id = int(data.replace("ytarc_vid_", ""))
        entry = await get_archive_entry(archive_id)
        if not entry:
            await query.answer("ویدیو در کش یافت نشد.", show_alert=True)
            return

        allowed, used, limit = await can_user_fetch_from_archive(user_id)
        if not allowed:
            await query.answer(
                f"محدودیت روزانه: {used}/{limit} دریافت از آرشیو.",
                show_alert=True,
            )
            return

        await query.answer("در حال ارسال...")
        file_ids = json.loads(entry["file_ids"])
        fmt = entry["format_type"] or "video_zip"
        await send_cached_files(context, user_id, file_ids, fmt)
        await increment_archive_fetch(user_id)
        await increment_yt_video_view(entry["video_id"])
        return

    if data == "ytarc_main":
        await _send_archive_overview(update, context)
        return


async def _show_channel_videos(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    channel_name: str,
    page: int = 0,
):
    query = update.callback_query
    offset = page * VIDEOS_PAGE_SIZE
    videos = await get_channel_videos_page(
        channel_name, offset=offset, limit=VIDEOS_PAGE_SIZE
    )
    total = await count_channel_videos(channel_name)
    total_pages = max(1, (total + VIDEOS_PAGE_SIZE - 1) // VIDEOS_PAGE_SIZE)

    if not videos:
        await query.answer("ویدیویی برای این کانال نیست.")
        return

    lines = [
        f"📺 **{channel_name}**\n",
        f"صفحه {page + 1} از {total_pages} — جدیدترین ویدیوها:\n",
    ]
    keyboard = []
    for row in videos:
        title = row["title"]
        if len(title) > 50:
            short = title[:47] + "…"
        else:
            short = title
        lines.append(f"• {short}")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"▶️ {short[:35]}",
                    callback_data=f"ytarc_vid_{row['id']}",
                )
            ]
        )

    nav = []
    enc = _encode_channel(channel_name)
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "◀️ قبلی",
                callback_data=f"ytarc_vidpg_{enc}_{page - 1}",
            )
        )
    if (page + 1) * VIDEOS_PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(
                "بعدی ▶️",
                callback_data=f"ytarc_vidpg_{enc}_{page + 1}",
            )
        )
    if nav:
        keyboard.append(nav)
    keyboard.append(
        [InlineKeyboardButton("📚 بازگشت به آرشیو", callback_data="ytarc_main")]
    )

    await query.answer()
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
