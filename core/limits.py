# limits.py

FREE_LIMITS = {
    "youtube_download": 1,
    "music_download": 6,
    "pinterest_search": 10,
    "tiktok_download": 5,
    "github_download": 2,
    "smart_abstract": 2,
    "citation": 2,
    "web_search": 1,
    "yt_archive": 2,
    "ai_chat": 2,
}

VIP_LIMITS = {
    "youtube_download": 20,
    "music_download": 20,
    "pinterest_search": 40,
    "tiktok_download": 30,
    "github_download": 20,
    "smart_abstract": 20,
    "citation": 20,
    "web_search": 30,
    "yt_archive": 20,
    "ai_chat": 20,
}


def get_limit(key: str, is_vip: int) -> int:
    limits = VIP_LIMITS if is_vip == 1 else FREE_LIMITS
    return limits[key]
