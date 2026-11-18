# core/yt_moderation.py

import re
import unicodedata

from core.database.yt_blacklist import (
    is_channel_blacklisted,
    get_all_blocked_words,
)

MSG_BLOCKED_CHANNEL = (
    "❌ دانلود از این کانال یوتیوب مجاز نیست."
)
MSG_BLOCKED_SEARCH = (
    "❌ جستجوی این عبارت مجاز نیست."
)

# Default seed (loaded into DB once). Admin can add/remove via /blockword
_DEFAULT_BLOCKED_WORDS = (
    "porn", "porno", "xxx", "hentai", "nude", "nudes", "nsfw",
    "sex", "sexy", "erotic", "milf", "anal", "blowjob", "orgasm",
    "xnxx", "xvideos", "pornhub", "redtube", "youporn", "xhamster",
    "onlyfans", "brazzers", "bangbros", "playboy",
    "سکس", "سکسی", "پورن", "پورنو", "جنس", "جنسی", "برهنه",
    "لخت", "حشری", "کیر", "کص", "کس", "جنده",
)


def _normalize_search_text(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[^\w\s\u0600-\u06ff]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


_compiled_matcher_key: tuple[str, ...] | None = None
_compiled_single_words: frozenset[str] = frozenset()
_compiled_phrase_re: re.Pattern | None = None


def _get_compiled_blocked_matcher(words: list[str]) -> tuple[frozenset[str], re.Pattern | None]:
    global _compiled_matcher_key, _compiled_single_words, _compiled_phrase_re
    cleaned = tuple(w.strip().lower() for w in words if w and w.strip())
    if cleaned == _compiled_matcher_key:
        return _compiled_single_words, _compiled_phrase_re

    singles = frozenset(w for w in cleaned if " " not in w)
    phrases = [w for w in cleaned if " " in w]
    phrase_re = (
        re.compile(r"(?:^|\s)(?:" + "|".join(re.escape(p) for p in phrases) + r")(?:\s|$)")
        if phrases
        else None
    )
    _compiled_matcher_key = cleaned
    _compiled_single_words = singles
    _compiled_phrase_re = phrase_re
    return singles, phrase_re


def _blocked_word_matches(blocked: str, normalized: str, tokens: set[str]) -> bool:
    """Match whole words/tokens only — avoids e.g. کس matching inside پادکست."""
    b = blocked.strip().lower()
    if not b:
        return False
    if " " in b:
        return bool(
            re.search(rf"(?:^|\s){re.escape(b)}(?:\s|$)", normalized)
        )
    return b in tokens


async def is_search_query_blocked(query: str) -> bool:
    normalized = _normalize_search_text(query)
    if not normalized:
        return False
    words = await get_all_blocked_words()
    if not words:
        words = list(_DEFAULT_BLOCKED_WORDS)
    singles, phrase_re = _get_compiled_blocked_matcher(words)
    tokens = set(normalized.split())
    if singles & tokens:
        return True
    if phrase_re is not None and phrase_re.search(normalized):
        return True
    return False


async def check_channel_allowed(channel_or_uploader: str) -> bool:
    if not channel_or_uploader:
        return True
    blocked = await is_channel_blacklisted(channel_or_uploader)
    return not blocked


async def check_video_info_allowed(info: dict | None) -> bool:
    if not info:
        return True
    names = [
        info.get("uploader"),
        info.get("channel"),
        info.get("channel_id"),
        info.get("uploader_id"),
    ]
    channel_url = (info.get("channel_url") or info.get("uploader_url") or "").rstrip("/")
    if channel_url:
        names.append(channel_url.rsplit("/", 1)[-1])
    if await is_channel_blacklisted(*[n for n in names if n]):
        return False
    title = info.get("title") or ""
    if await is_search_query_blocked(title):
        return False
    return True


def get_default_blocked_words_seed():
    return list(_DEFAULT_BLOCKED_WORDS)
