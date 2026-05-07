from datetime import datetime
import pytz

TEHRAN_TZ = pytz.timezone("Asia/Tehran")


def get_tehran_today():
    return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")


def get_tehran_now_full():
    return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
