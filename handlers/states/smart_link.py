# handlers/states/smart_link.py

from dataclasses import dataclass
import ipaddress
import re
import uuid
from urllib.parse import parse_qs, urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.database import get_setting
from core.state_manager import StateCache
from core.task_utils import track_task
from core.yt_moderation import MSG_BLOCKED_CHANNEL, check_video_info_allowed
from handlers.ensure_membership import ensure_membership
from handlers.utils import safe_answer_query
from services import telegram_telethon
from services.youtube import get_video_info_cached

from .state_github import _normalize_github_repo, start_github_repo_download
from .state_insta import start_insta_download
from .state_kaggle import _parse_kaggle_ref, start_kaggle_dataset_download
from .state_programming import handle_programming_state
from .state_telegram import handle_telegram_state
from .state_tiktok import start_tiktok_link_download
from .state_web_search import _download_and_send_webpage
from .youtube.callbacks import create_yt_link_session
from .youtube.helpers import check_user_limit
from .youtube.state_handler import handle_youtube_state

_URL_RE = re.compile(r"https?://[^\s<>'\"`]+", re.IGNORECASE)
_BARE_KNOWN_URL_RE = re.compile(
    r"(?:^|\s)((?:(?:www|m|vm|vt|music)\.)?"
    r"(?:youtube\.com|youtu\.be|instagram\.com|instagr\.am|tiktok\.com|"
    r"t\.me|telegram\.me|telegram\.dog|github\.com|kaggle\.com|"
    r"chromewebstore\.google\.com|chrome\.google\.com/webstore|"
    r"marketplace\.visualstudio\.com|addons\.mozilla\.org)"
    r"/[^\s<>'\"`]+)",
    re.IGNORECASE,
)
_TRAILING_PUNCT = ".,;:!?)»]}\"'،؛"

_GITHUB_RESERVED_OWNERS = frozenset(
    {
        "about",
        "account",
        "codespaces",
        "collections",
        "contact",
        "customer-stories",
        "enterprise",
        "events",
        "explore",
        "features",
        "gist",
        "import",
        "issues",
        "join",
        "login",
        "marketplace",
        "new",
        "notifications",
        "orgs",
        "pricing",
        "pulls",
        "resources",
        "search",
        "security",
        "settings",
        "signup",
        "site",
        "solutions",
        "sponsors",
        "topics",
        "trending",
    }
)

_TELEGRAM_RESERVED_PATHS = frozenset(
    {
        "addemoji",
        "addlist",
        "addstickers",
        "bg",
        "boost",
        "c",
        "confirmphone",
        "giftcode",
        "iv",
        "joinchat",
        "login",
        "nft",
        "proxy",
        "setlanguage",
        "share",
        "socks",
    }
)

_smart_web_cache = StateCache(max_capacity=2000, default_ttl=3600.0)


@dataclass(frozen=True)
class DetectedLink:
    kind: str
    url: str
    target: str


def _clean_url(raw: str) -> str:
    return (raw or "").strip().rstrip(_TRAILING_PUNCT)


def _extract_url(text: str) -> str | None:
    if not text:
        return None
    m = _URL_RE.search(text)
    if m:
        url = _clean_url(m.group(0))
        return url or None
    m_bare = _BARE_KNOWN_URL_RE.search(text)
    if m_bare:
        bare = _clean_url(m_bare.group(1))
        return f"https://{bare}" if bare else None
    return None


def _is_public_web_host(host: str) -> bool:
    if not host or "." not in host:
        return False
    lower = host.lower()
    if lower in ("localhost", "localhost.localdomain") or lower.endswith(
        (".local", ".internal", ".localhost")
    ):
        return False
    try:
        ip = ipaddress.ip_address(lower)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    except ValueError:
        pass
    return True


def detect_link(text: str) -> DetectedLink | None:
    url = _extract_url(text)
    if not url:
        return None

    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()
    if not host:
        return None

    path = parsed.path or ""
    path_parts = [p for p in path.split("/") if p]
    query = parse_qs(parsed.query)

    # 1. YouTube (video / shorts / live / music / channel)
    if host == "youtu.be" and path_parts:
        return DetectedLink("youtube_video", url, url)

    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if (
            path.startswith(("/watch", "/shorts/", "/live/", "/embed/", "/v/"))
            or "v" in query
        ):
            return DetectedLink("youtube_video", url, url)
        if path_parts and path_parts[0].startswith("@") and len(path_parts[0]) > 1:
            return DetectedLink("youtube_channel", url, path_parts[0])

    # 2. Instagram (post / reel / tv / stories / share)
    if host in ("instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am"):
        if path_parts and path_parts[0].lower() in (
            "p",
            "reel",
            "reels",
            "tv",
            "stories",
            "share",
        ):
            return DetectedLink("instagram", url, url)

    # 3. TikTok
    if (host == "tiktok.com" or host.endswith(".tiktok.com")) and path_parts:
        return DetectedLink("tiktok", url, url)

    # 4. Telegram (single post or public channel)
    if host in ("t.me", "telegram.me", "telegram.dog") and path_parts:
        if telegram_telethon.parse_message_link(url):
            return DetectedLink("telegram_post", url, url)
        first = path_parts[0]
        if first.lower() == "s" and len(path_parts) >= 2:
            chan = path_parts[1]
        elif first.lower() not in _TELEGRAM_RESERVED_PATHS and not first.startswith("+"):
            chan = first
        else:
            chan = ""
        if chan and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", chan):
            return DetectedLink("telegram_channel", url, chan)

    # 5. GitHub repository
    if host in ("github.com", "www.github.com") and len(path_parts) >= 2:
        if path_parts[0].lower() not in _GITHUB_RESERVED_OWNERS:
            repo = _normalize_github_repo(url)
            if repo:
                return DetectedLink("github_repo", url, repo)

    # 6. Kaggle dataset
    if host in ("kaggle.com", "www.kaggle.com"):
        ref = _parse_kaggle_ref(url)
        if ref:
            return DetectedLink("kaggle_dataset", url, ref)

    # 7. Chrome Web Store extension
    if host == "chromewebstore.google.com" or (
        host == "chrome.google.com" and path.startswith("/webstore")
    ):
        ext_match = re.search(r"/([a-z]{32})(?:[/?#]|$)", url)
        if ext_match:
            return DetectedLink("chrome_extension", url, ext_match.group(1))

    # 8. VS Code Marketplace extension
    if host == "marketplace.visualstudio.com":
        item_name = (query.get("itemName") or [""])[0].strip()
        if item_name and re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+", item_name):
            return DetectedLink("vscode_extension", url, item_name)

    # 9. Firefox Add-on
    if host == "addons.mozilla.org":
        addon_match = re.search(r"/addon/([^/?#]+)", path, re.IGNORECASE)
        if addon_match:
            return DetectedLink("firefox_addon", url, addon_match.group(1))

    # 10. Generic web page (only if original text explicitly had http:// or https://)
    if _URL_RE.search(text) and _is_public_web_host(host):
        return DetectedLink("web_page", url, url)

    return None


async def _handle_smart_youtube_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    chat_id: str,
) -> None:
    if await get_setting("youtube_enabled", "1") == "0":
        await update.message.reply_text(
            "❌ بخش یوتیوب فعلاً توسط ادمین غیرفعال شده است."
        )
        return

    if not await check_user_limit(chat_id):
        await update.message.reply_text(
            "❌ محدودیت دانلود روزانه شما ($ 1 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
        )
        return

    status_msg = await update.message.reply_text(
        "📺 لینک یوتیوب شناسایی شد!\n⏳ در حال بررسی ویدیو..."
    )
    try:
        info = await get_video_info_cached(url)
    except Exception:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            "❌ خطا در دریافت اطلاعات ویدیو. لطفاً دوباره تلاش کنید."
        )
        return

    try:
        await status_msg.delete()
    except Exception:
        pass

    if not info:
        await update.message.reply_text(
            "❌ ویدیو پیدا نشد یا یوتیوب در دسترس نیست. لینک را بررسی کنید."
        )
        return

    if not await check_video_info_allowed(info):
        await update.message.reply_text(MSG_BLOCKED_CHANNEL)
        return

    token = create_yt_link_session(
        chat_id,
        yt_url=url,
        format_type=None,
        step="waiting_yt_format",
    )
    title = (info.get("title") or "").strip()
    title_line = f"🎬 {title[:120]}\n\n" if title else ""
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎥 دانلود ویدیو (تصویری)",
                    callback_data=f"ytfmt_video_{token}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🎵 دانلود فایل صوتی (MP3)",
                    callback_data=f"ytfmt_audio_{token}",
                )
            ],
        ]
    )
    await update.message.reply_text(
        f"📺 لینک یوتیوب شناسایی شد!\n{title_line}فرمت دانلود را انتخاب کنید 👇",
        reply_markup=keyboard,
    )


async def try_handle_smart_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    chat_id: str,
) -> bool:
    """Detect supported URLs when user is idle (no active state) and route automatically."""
    detected = detect_link(text)
    if detected is None:
        return False

    if not await ensure_membership(update, context):
        return True

    kind = detected.kind

    if kind == "youtube_video":
        await _handle_smart_youtube_video(update, context, detected.url, chat_id)
        return True

    if kind == "youtube_channel":
        if await get_setting("youtube_enabled", "1") == "0":
            await update.message.reply_text(
                "❌ بخش یوتیوب فعلاً توسط ادمین غیرفعال شده است."
            )
            return True
        await handle_youtube_state(
            update, context, "waiting_yt_last5_channel", detected.target, chat_id, {}
        )
        return True

    if kind == "instagram":
        await start_insta_download(
            update, context, detected.url, chat_id, keep_state=False
        )
        return True

    if kind == "tiktok":
        await start_tiktok_link_download(
            update, context, detected.url, chat_id, keep_state=False
        )
        return True

    if kind == "telegram_post":
        await handle_telegram_state(
            update,
            context,
            "waiting_tg_single",
            detected.url,
            chat_id,
            {},
            keep_state=False,
        )
        return True

    if kind == "telegram_channel":
        await handle_telegram_state(
            update,
            context,
            "waiting_tg_latest",
            detected.target,
            chat_id,
            {},
            keep_state=False,
        )
        return True

    if kind == "github_repo":
        await start_github_repo_download(
            update, context, detected.target, chat_id, keep_state=False
        )
        return True

    if kind == "kaggle_dataset":
        await start_kaggle_dataset_download(
            update, context, detected.target, chat_id, keep_state=False
        )
        return True

    if kind == "chrome_extension":
        await handle_programming_state(
            update,
            context,
            "waiting_prog_chrome",
            detected.target,
            chat_id,
            {},
            keep_state=False,
        )
        return True

    if kind == "vscode_extension":
        await handle_programming_state(
            update,
            context,
            "waiting_prog_vscode",
            detected.target,
            chat_id,
            {},
            keep_state=False,
        )
        return True

    if kind == "firefox_addon":
        await handle_programming_state(
            update,
            context,
            "waiting_prog_firefox",
            detected.target,
            chat_id,
            {},
            keep_state=False,
        )
        return True

    if kind == "web_page":
        token = uuid.uuid4().hex[:12]
        _smart_web_cache[token] = {"chat_id": str(chat_id), "url": detected.url}
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📄 دانلود صفحه وب (HTML)",
                        callback_data=f"smartweb_{token}",
                    )
                ]
            ]
        )
        await update.message.reply_text(
            "🌐 لینک وب‌سایت شناسایی شد.\n"
            "برای ذخیره کامل این صفحه به صورت فایل HTML، روی دکمه زیر کلیک کنید:",
            reply_markup=keyboard,
        )
        return True

    return False


async def smart_web_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)

    if not await ensure_membership(update, context):
        return

    data = query.data or ""
    if not data.startswith("smartweb_"):
        return

    token = data.split("smartweb_", 1)[1]
    chat_id = str(query.message.chat_id)
    entry = _smart_web_cache.pop(token, None)
    if not entry or str(entry.get("chat_id")) != chat_id:
        await query.edit_message_text(
            "❌ نشست منقضی شده است. لطفاً لینک را مجدداً ارسال کنید."
        )
        return

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    target_url = entry["url"]
    user_id = update.effective_user.id if update.effective_user else int(chat_id)
    track_task(
        _download_and_send_webpage(
            query.message,
            context,
            chat_id,
            user_id,
            target_url,
            filename="WebPage.html",
            caption_label="🔗 لینک",
            wait_text="⏳ در حال پردازش و دریافت صفحه (ممکن است کمی طول بکشد)...",
            fail_text="❌ متاسفانه دریافت این صفحه با مشکل مواجه شد.\n\n(ممکن است سایت محافظت شده باشد یا لینک اشتباه باشد)",
        ),
        name=f"smart_web_{chat_id}",
    )
