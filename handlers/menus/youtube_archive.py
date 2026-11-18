# handlers/menus/youtube_archive.py

import asyncio
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
from core.keyboards import get_yt_archive_menu_keyboard, get_youtube_menu_keyboard, get_back_only_keyboard
from core.state_manager import StateCache, set_state, clear_state
from core.task_utils import track_task
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
from handlers.states.youtube.helpers import parse_quality_from_cache_key


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
    vip, total_global, channels, total_ch = await asyncio.gather(
        is_vip(user_id),
        count_user_archive(),
        get_user_channels_page(offset=0, limit=CHANNELS_PAGE_SIZE),
        count_user_channels(),
    )
    _, used, limit = await can_user_fetch_from_archive(user_id, is_vip_status=vip)

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


async def _prompt_archive_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    prompt_text: str,
):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, step)
    await update.message.reply_text(
        prompt_text,
        reply_markup=get_back_only_keyboard(),
    )


async def btn_yt_cache_search_title_req(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await _prompt_archive_search(
        update, context, "waiting_yt_archive_search_title", "عنوان یا بخشی از موضوع ویدیو را بنویسید:"
    )


async def btn_yt_cache_search_channel_req(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await _prompt_archive_search(
        update, context, "waiting_yt_archive_search_channel", "نام کانال یا بخشی از آن را بنویسید:"
    )


async def yt_archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
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
        try:
            page = int(data.split("_")[-1])
        except ValueError:
            await query.answer("صفحه نامعتبر است.")
            return
        offset = page * CHANNELS_PAGE_SIZE
        channels, total_ch = await asyncio.gather(
            get_user_channels_page(offset=offset, limit=CHANNELS_PAGE_SIZE),
            count_user_channels(),
        )
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
        try:
            page = int(parts[2])
            index = int(parts[3])
        except (IndexError, ValueError):
            await query.answer("درخواست نامعتبر است.")
            return
        offset = page * CHANNELS_PAGE_SIZE
        channels = await get_user_channels_page(offset=offset, limit=CHANNELS_PAGE_SIZE)
        if index >= len(channels):
            await query.answer("کانال یافت نشد.")
            return
        channel_name = channels[index]["channel_name"]
        if not await check_channel_allowed(channel_name):
            await query.answer(MSG_BLOCKED_CHANNEL, show_alert=True)
            return
        _set_ytarc_ui(user_id, channel=channel_name)
        await _show_channel_videos(update, context, channel_name, page=0)
        return

    if data.startswith("ytarc_vidpg_"):
        encoded = data.replace("ytarc_vidpg_", "", 1)
        try:
            channel_name, vid_page_str = encoded.rsplit("_", 1)
            vid_page = int(vid_page_str)
        except ValueError:
            await query.answer("درخواست نامعتبر است.")
            return
        channel_name = _decode_channel(channel_name)
        await _show_channel_videos(update, context, channel_name, page=vid_page)
        return

    if data.startswith("ytarc_pick_"):
        try:
            rep_id = int(data.replace("ytarc_pick_", ""))
        except ValueError:
            await query.answer("شناسه نامعتبر است.")
            return
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
            _set_ytarc_ui(user_id, pending_rowid=variants[0]["id"])
            await _send_archive_video(
                update, context, user_id, variants[0]["id"], preloaded_entry=variants[0]
            )
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
        vid_page = _get_ytarc_ui(user_id).get("vid_page", 0)
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
        try:
            archive_id = int(data.replace("ytarc_vid_", ""))
        except ValueError:
            await query.answer("شناسه نامعتبر است.")
            return
        await _send_archive_video(update, context, user_id, archive_id)
        return

    if data == "ytarc_main":
        await _send_archive_overview(update, context)
        return


async def _deliver_archive_video_bg(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    vip,
    video_id: str,
    file_ids: list,
    fmt: str,
):
    from handlers.states.youtube.helpers import send_cached_files

    try:
        await send_cached_files(context, user_id, file_ids, fmt)
    except Exception as e:
        print(f"yt archive send error: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ ارسال از کش ناموفق بود. لطفاً دوباره تلاش کنید.",
        )
        return
    await increment_archive_fetch(user_id, is_vip_status=vip)
    await increment_yt_video_view(video_id)


async def _send_archive_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    archive_id: int,
    *,
    preloaded_entry=None,
):
    from services.rate_limiter import user_action_lock

    query = update.callback_query
    async with user_action_lock(user_id, "yt_archive", timeout_sec=15) as acquired:
        if not acquired:
            if query:
                await query.answer("⏳ درخواست قبلی شما در حال ارسال است.", show_alert=True)
            return

        entry = preloaded_entry if preloaded_entry is not None else await get_archive_entry(archive_id)
        if not entry:
            if query:
                await query.answer("ویدیو در کش یافت نشد.", show_alert=True)
            return

        ch_blocked, word_blocked, vip = await asyncio.gather(
            is_channel_blacklisted(_row_str(entry, "channel_name")),
            is_search_query_blocked(_row_str(entry, "title")),
            is_vip(user_id),
        )
        if ch_blocked:
            await query.answer(MSG_BLOCKED_CHANNEL, show_alert=True)
            return
        if word_blocked:
            await query.answer(MSG_BLOCKED_SEARCH, show_alert=True)
            return

        allowed, used, limit = await can_user_fetch_from_archive(
            user_id, is_vip_status=vip
        )
        if not allowed:
            period = archive_limit_period_label(vip)
            await query.answer(
                f"محدودیت {period}: {used}/{limit} دریافت از آرشیو.",
                show_alert=True,
            )
            return

        try:
            file_ids = json.loads(entry["file_ids"] or "[]")
        except (json.JSONDecodeError, TypeError):
            await query.answer("فایل کش خراب است.", show_alert=True)
            return
        if not file_ids:
            await query.answer("فایل کش خالی است.", show_alert=True)
            return

        await query.answer("در حال ارسال...")
        fmt = entry["format_type"] or "video_zip"
        track_task(
            _deliver_archive_video_bg(
                context, user_id, vip, entry["video_id"], file_ids, fmt
            ),
            name=f"yt_archive_send_{user_id}",
        )


_backfill_inflight = StateCache(max_capacity=500, default_ttl=600.0)
_ytarc_ui_state = StateCache(max_capacity=5000, default_ttl=3600.0)


def _get_ytarc_ui(user_id: str) -> dict:
    return _ytarc_ui_state.get(str(user_id)) or {}


def _set_ytarc_ui(user_id: str, **updates) -> None:
    key = str(user_id)
    cur = dict(_ytarc_ui_state.get(key) or {})
    cur.update(updates)
    _ytarc_ui_state[key] = cur


def _schedule_missing_upload_date_backfill(videos: list) -> None:
    missing_rows = []
    for row in videos:
        try:
            existing = row["uploaded_at"]
            vid = row["video_id"]
        except (KeyError, IndexError, TypeError):
            continue
        if (not existing or not str(existing).strip()) and vid not in _backfill_inflight:
            _backfill_inflight[vid] = 1
            missing_rows.append(dict(row))

    if missing_rows:
        track_task(
            backfill_upload_dates_for_cache_rows(missing_rows),
            name="yt_archive_upload_date_backfill",
        )


async def _show_channel_videos(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    channel_name: str,
    page: int = 0,
):
    query = update.callback_query
    offset = page * VIDEOS_PAGE_SIZE
    videos, total = await asyncio.gather(
        get_channel_videos_page(channel_name, offset=offset, limit=VIDEOS_PAGE_SIZE),
        count_channel_videos(channel_name),
    )
    if videos:
        _schedule_missing_upload_date_backfill(videos)
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

    uid_key = str(query.from_user.id) if query and query.from_user else ""
    if uid_key:
        _set_ytarc_ui(uid_key, vid_page=page)

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
