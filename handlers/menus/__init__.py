from .common import btn_back_action

from .youtube import (
    btn_yt_req,
    btn_yt_last5_req,
    btn_yt_ch_search_req,
    btn_yt_global_req,
    btn_yt_link_vid_req,
    btn_yt_link_mp3_req,
    btn_yt_top_videos_req,
)
from .youtube_archive import (
    btn_yt_my_cache_req,
    btn_yt_cache_search_title_req,
    btn_yt_cache_search_channel_req,
    yt_archive_callback,
    handle_yt_archive_search_state,
)

from .ai import (
    btn_ai_menu,
    btn_ai_chat_req,
    btn_ai_ocr_req,
    btn_ai_tts_req,
    btn_ai_image_req,
)

from .telegram_menu import (
    btn_telegram_menu,
    btn_tg_single_req,
    btn_tg_latest_req,
)

from .instagram import (
    btn_ig_req,
    btn_ig_link_dl_req,
)

from .translation import (
    btn_tr_help,
    btn_tr_fa_en_req,
    btn_tr_en_fa_req,
)

from .weather import btn_weather_req

from .support import (
    btn_support_req,
    btn_profile_req,
)

from .programming import (
    btn_programming_menu,
    btn_prog_chrome_req,
    btn_prog_firefox_req,
    btn_prog_vscode_req,
)

from .music import (
    btn_music_menu,
    btn_music_track_req,
    btn_music_album_req,
    btn_music_artist_req,
    btn_music_playlist_req,
)

from .pinterest import btn_pinterest_req

from .tiktok import (
    btn_tiktok_req,
    btn_tt_link_req,
    btn_tt_search_req,
    btn_tt_trend_req,
    btn_tt_explore_req,
)

from .github import (
    btn_prog_github_menu,
    btn_gh_dl_req,
    btn_gh_user_req,
    btn_gh_search_req,
)

from .web_scraper import (
    btn_web_search_req,
    btn_google_search_subject_req,
    btn_google_search_link_req,
)
