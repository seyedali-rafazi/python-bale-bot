# core/database/__init__.py

from .base import DB_NAME
from .utils import get_tehran_today, get_tehran_now_full, get_tehran_archive_week_key
from .init_db import init_db
from .settings import get_setting, set_setting
from .transactions import add_transaction
from .users import (
    add_user,
    set_vip,
    get_user_info,
    get_full_user_info,
    get_total_users,
    get_all_users,
    reset_user_limits,
    get_web_search_downloads,
    increment_web_search_downloads,
)
from .vip import (
    is_vip,
    add_vip_time,
    get_total_vip_users,
    add_vip_time_to_all,
    set_vip_expire_date,
)
from .music import get_music_downloads, increment_music_downloads
from .youtube import (
    get_yt_downloads,
    increment_yt_downloads,
    decrement_yt_downloads,
    get_cached_video,
    save_cached_video,
    increment_yt_video_view,
    get_top_cached_videos,
    count_global_cache,
    count_cache_needing_metadata,
    backfill_youtube_cache_metadata,
    purge_incomplete_youtube_cache,
    purge_all_youtube_cache,
    drop_legacy_user_youtube_archive_table,
)
from .yt_blacklist import (
    add_channel_blacklist,
    remove_channel_blacklist,
    list_channel_blacklist,
    add_blocked_word,
    remove_blocked_word,
    list_blocked_words,
)
from .pinterest import get_pinterest_downloads, increment_pinterest_downloads
from .tiktok import get_tt_downloads, increment_tt_downloads
from .github import get_gh_downloads, increment_gh_downloads
from .telegram import get_tg_downloads, increment_tg_downloads
from .kaggle import (
    get_kaggle_downloads,
    increment_kaggle_downloads,
    KAGGLE_LIMIT_FREE,
    KAGGLE_LIMIT_VIP,
)
from .cloud import (
    get_user_cloud_info,
    get_available_cloud_mb,
    add_cloud_storage,
    reduce_cloud_storage,
    add_cloud_file,
    get_user_cloud_files,
    delete_cloud_file,
    get_cloud_usage_stats,
    give_5gb_to_existing_vips,
)
from .web_scrapping import increment_web_search_downloads, get_web_search_downloads
from .user_yt_archive import (
    get_user_archive_limit,
    count_user_archive,
    get_user_channels_page,
    count_user_channels,
    get_channel_videos_page,
    count_channel_videos,
    get_archive_entry,
    get_archive_variants,
    dedupe_archive_rows,
    search_archive_by_title,
    search_archive_by_channel,
    can_user_fetch_from_archive,
    increment_archive_fetch,
    get_archive_fetches_today,
    get_archive_fetches_used,
    archive_limit_period_label,
    ARCHIVE_LIMIT_FREE,
    ARCHIVE_LIMIT_VIP,
    CHANNELS_PAGE_SIZE,
    VIDEOS_PAGE_SIZE,
)
from .user_ai import (
    get_user_ai_limit,
    get_ai_questions_today,
    can_user_ask_ai,
    increment_ai_question,
    AI_LIMIT_FREE,
    AI_LIMIT_VIP,
)
from .monitoring import (
    log_monitor_event,
    log_upload_success,
    log_user_active,
    get_monitoring_report_data,
    count_active_users_today,
    purge_old_monitoring_events,
    SECTION_LABELS,
    ALL_SECTIONS,
)
