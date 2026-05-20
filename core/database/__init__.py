# core/database/__init__.py

from .base import DB_NAME
from .utils import get_tehran_today, get_tehran_now_full
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
)
from .pinterest import get_pinterest_downloads, increment_pinterest_downloads
from .tiktok import (
    get_tt_downloads,
    increment_tt_downloads,
    get_tt_explores,
    increment_tt_explores,
    add_tiktok_explore_video,
    get_random_tiktok_explore_videos,
    delete_invalid_video_from_db,
)
from .github import get_gh_downloads, increment_gh_downloads
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
