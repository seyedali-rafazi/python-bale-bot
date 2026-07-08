# handlers/menus/youtube_archive.py

import json
from urllib.parse import quote

from core.database.youtube import backfill_upload_dates_for_cache_rows

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
    get_archive_variants,
    dedupe_archive_rows,
    can_user_fetch_from_archive,
    increment_archive_fetch,
    increment_yt_video_view,
    log_upload_success,
    CHANNELS_PAGE_SIZE,
    VIDEOS_PAGE_SIZE,
    ARCHIVE_LIMIT_FREE,
    ARCHIVE_LIMIT_VIP,
    archive_limit_period_label,
)
from core.database.youtube import archive_row_yt_id
from core.database.vip import is_vip
from core.yt_moderation import (
    MSG_BLOCKED_CHANNEL,
    MSG_BLOCKED_SEARCH,
    check_channel_allowed,
    is_search_query_blocked,
)
from core.database.yt_blacklist import is_channel_blacklisted
from handlers.ensure_membership import ensure_membership


def _channel_callback_data(page: int, index: int) -> str:
    return f"ytarc_ch_{page}_{index}"


def _encode_channel(channel_name: str) -> str:
    return quote(channel_name, safe="")


def _decode_channel(encoded: str) -> str:
    from urllib.parse import unquote

    return unquote(encoded)


def _variant_button_label(row) -> str:
    fmt = _row_str(row, "format_type", "video_zip")
    quality = _row_str(row, "quality", "")
    if not quality:
        from handlers.states.youtube.helpers import parse_quality_from_cache_key

        quality = parse_quality_from_cache_key(_row_str(row, "video_id"))
    if "audio" in fmt:
        return "🎵 صوتی (MP3)"
    return f"📺 {quality}p"


def _row_str(row, key: str, default: str = "") -> str:
    """sqlite3.Row has no .get(); use bracket access safely."""
    try:
        val = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if val is None else str(val)


async def _send_archive_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    total_global = await count_user_archive()
    limit = await get_user_archive_limit(user_id)
    _, used, _ = await can_user_fetch_from_archive(user_id)
    vip = await is_vip(user_id)

    plan = "Pro" if vip == 1 else "رایگان"
    period_label = archive_limit_period_label(vip)
    free_hint = (
        f"رایگان: {ARCHIVE_LIMIT_FREE} در هفته (ریست شنبه نیمه‌شب تهران)"
    )
    vip_hint = f"Pro: {ARCHIVE_LIMIT_VIP} در روز (ریست نیمه‌شب تهران)"
    feature_text = (
        "📚 **کش مشترک ویدیوهای یوتیوب**\n\n"
        "وقتی هر کاربری ویدیویی دانلود کند، برای **همه** در این آرشیو "
        "ذخیره می‌شود و بدون دانلود مجدد قابل دریافت است.\n\n"
        f"🌐 تعداد ویدیو در کش سرور: **{total_global}**\n"
        f"👤 اشتراک شما: **{plan}**\n"
        f"📥 دریافت از آرشیو ({period_label}): **{used}** از **{limit}**\n"
        f"({free_hint} | {vip_hint})\n\n"
        "روی کانال بزنید — ویدیوها بر اساس **تاریخ انتشار در یوتیوب** (جدیدترین اول) مرتب شده‌اند."
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
        channels = await get_user_channels_page(offset=0, limit=CHANNELS_PAGE_SIZE)
        total_ch = await count_user_channels()
        keyboard = _build_channels_keyboard(channels, page=0, total_channels=total_ch)

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
            InlineKeyboardButton(
                "◀️ ۵ کانال قبل", callback_data=f"ytarc_chpg_{page - 1}"
            )
        )
    if (page + 1) * CHANNELS_PAGE_SIZE < total_channels:
        nav.append(
            InlineKeyboardButton(
                "۵ کانال بعد ▶️", callback_data=f"ytarc_chpg_{page + 1}"
            )
        )
    nav.append(InlineKeyboardButton("🔄 بروزرسانی", callback_data="ytarc_refresh"))
    if nav:
        rows.append(nav)

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


async def yt_archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = str(query.from_user.id)

    if data == "ytarc_refresh":
        await query.answer()
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
        channels = await get_user_channels_page(offset=offset, limit=CHANNELS_PAGE_SIZE)
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
        channels = await get_user_channels_page(offset=offset, limit=CHANNELS_PAGE_SIZE)
        if index >= len(channels):
            await query.answer("کانال یافت نشد.")
            return
        channel_name = channels[index]["channel_name"]
        if not await check_channel_allowed(channel_name):
            await query.answer(MSG_BLOCKED_CHANNEL, show_alert=True)
            return
        context.user_data["ytarc_channel"] = channel_name
        await _show_channel_videos(update, context, channel_name, page=0)
        return

    if data.startswith("ytarc_vidpg_"):
        encoded = data.replace("ytarc_vidpg_", "", 1)
        channel_name, vid_page = encoded.rsplit("_", 1)
        channel_name = _decode_channel(channel_name)
        await _show_channel_videos(update, context, channel_name, page=int(vid_page))
        return

    if data.startswith("ytarc_pick_"):
        rep_id = int(data.replace("ytarc_pick_", ""))
        entry = await get_archive_entry(rep_id)
        if not entry:
            await query.answer("ویدیو در کش یافت نشد.", show_alert=True)
            return

        channel_name = _row_str(entry, "channel_name")
        yt_id = archive_row_yt_id(entry)
        if not yt_id:
            await query.answer("شناسه ویدیو نامعتبر است.", show_alert=True)
            return

        variants = await get_archive_variants(channel_name, yt_id)
        if not variants:
            await query.answer("فایلی در کش نیست.", show_alert=True)
            return

        if len(variants) == 1:
            context.user_data["ytarc_pending_rowid"] = variants[0]["id"]
            await _send_archive_video(update, context, user_id, variants[0]["id"])
            return

        title = _row_str(entry, "title") or yt_id
        if len(title) > 50:
            title = title[:47] + "…"
        lines = [
            f"📺 **{title}**",
            "",
            "چند کیفیت در کش موجود است. یکی را انتخاب کنید:",
        ]
        keyboard = [
            [
                InlineKeyboardButton(
                    _variant_button_label(v),
                    callback_data=f"ytarc_vid_{v['id']}",
                )
            ]
            for v in variants
        ]
        vid_page = context.user_data.get("ytarc_vid_page", 0)
        enc = _encode_channel(channel_name)
        keyboard.append(
            [
                InlineKeyboardButton(
                    "◀️ بازگشت به لیست",
                    callback_data=f"ytarc_vidpg_{enc}_{vid_page}",
                )
            ]
        )
        await query.answer()
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return

    if data.startswith("ytarc_vid_"):
        archive_id = int(data.replace("ytarc_vid_", ""))
        await _send_archive_video(update, context, user_id, archive_id)
        return

    if data == "ytarc_main":
        await _send_archive_overview(update, context)
        return


async def _send_archive_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    archive_id: int,
):
    query = update.callback_query
    entry = await get_archive_entry(archive_id)
    if not entry:
        if query:
            await query.answer("ویدیو در کش یافت نشد.", show_alert=True)
        return

    if await is_channel_blacklisted(_row_str(entry, "channel_name")):
        await query.answer(MSG_BLOCKED_CHANNEL, show_alert=True)
        return
    if await is_search_query_blocked(_row_str(entry, "title")):
        await query.answer(MSG_BLOCKED_SEARCH, show_alert=True)
        return

    allowed, used, limit = await can_user_fetch_from_archive(user_id)
    if not allowed:
        vip = await is_vip(user_id)
        period = archive_limit_period_label(vip)
        await query.answer(
            f"محدودیت {period}: {used}/{limit} دریافت از آرشیو.",
            show_alert=True,
        )
        return

    await query.answer("در حال ارسال...")
    from handlers.states.youtube.helpers import send_cached_files

    try:
        file_ids = json.loads(entry["file_ids"] or "[]")
    except (json.JSONDecodeError, TypeError):
        await query.answer("فایل کش خراب است.", show_alert=True)
        return
    if not file_ids:
        await query.answer("فایل کش خالی است.", show_alert=True)
        return

    fmt = entry["format_type"] or "video_zip"
    try:
        await send_cached_files(context, user_id, file_ids, fmt)
    except Exception as e:
        print(f"yt archive send error: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ ارسال از کش ناموفق بود. لطفاً دوباره تلاش کنید.",
        )
        return
    await increment_archive_fetch(user_id)
    await log_upload_success("yt_archive", user_id)
    await increment_yt_video_view(entry["video_id"])


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
    if videos:
        await backfill_upload_dates_for_cache_rows(videos)
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
        f"صفحه {page + 1} از {total_pages} — جدیدترین انتشار در کانال:\n",
    ]
    keyboard = []
    for row in videos:
        title = row["title"] or row["yt_video_id"] or "ویدیو"
        if len(title) > 50:
            short = title[:47] + "…"
        else:
            short = title
        pub = _row_str(row, "uploaded_at")
        if len(pub) >= 8:
            pub_label = f"{pub[:4]}/{pub[4:6]}/{pub[6:8]}"
            lines.append(f"• {short} — 📅 {pub_label}")
        else:
            lines.append(f"• {short}")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"▶️ {short[:35]}",
                    callback_data=f"ytarc_pick_{row['id']}",
                )
            ]
        )

    context.user_data["ytarc_vid_page"] = page

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
