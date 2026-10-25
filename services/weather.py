# services/weather.py

import aiohttp
import asyncio
import urllib.parse
from services.http_client import get_http_session


def get_wmo_description(code):
    weather_codes = {
        0: ("صاف و آفتابی", "☀️"),
        1: ("عمدتاً صاف", "🌤"),
        2: ("نیمه ابری", "⛅️"),
        3: ("ابری", "☁️"),
        45: ("مه‌آلود", "🌫"),
        48: ("مه همراه با یخ‌زدگی", "❄️🌫"),
        51: ("نم‌نم باران", "🌦"),
        61: ("بارانی", "☔️"),
        71: ("برفی", "🌨"),
        95: ("رعد و برق", "🌩"),
    }
    return weather_codes.get(code, ("نامشخص", "🌍"))


async def get_weather_forecast(city_name: str) -> str:
    try:
        clean_name = city_name.strip()
        if not clean_name:
            return "❌ لطفاً نام شهر را وارد کنید."

        # Check Cache (30 min)
        from services.cache_service import cache_get, cache_set
        cache_key = f"weather:{clean_name.lower()}"
        cached_forecast = await cache_get(cache_key)
        if cached_forecast:
            return cached_forecast

        timeout = aiohttp.ClientTimeout(total=15)
        session = await get_http_session()

        # بررسی زبان ورودی (فارسی یا انگلیسی)
        is_farsi = any(ord(c) > 127 for c in clean_name)
        langs = ["fa", "en"] if is_farsi else ["en", "fa"]

        location = None
        for lang in langs:
            encoded_name = urllib.parse.quote(clean_name)
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_name}&count=1&language={lang}&format=json"
            async with session.get(geo_url, timeout=timeout) as geo_resp:
                if geo_resp.status == 200:
                    geo_data = await geo_resp.json()
                    results = geo_data.get("results")
                    if results:
                        location = results[0]
                        break

        if not location:
            return f"❌ شهری با نام `{clean_name}` پیدا نشد."

        lat, lon = location["latitude"], location["longitude"]
        city = location.get("name", clean_name)
        country = location.get("country", "نامشخص")

        # 2. دریافت وضعیت آب و هوا با مختصات
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=3"
        )
        async with session.get(weather_url, timeout=timeout) as weather_resp:
            weather_data = await weather_resp.json()

        daily = weather_data.get("daily", {})
        result_text = f"🌍 **پیش‌بینی آب و هوای {city}** ({country})\n\n"

        for i in range(len(daily.get("time", []))):
            date_str = daily["time"][i]
            max_t = daily["temperature_2m_max"][i]
            min_t = daily["temperature_2m_min"][i]
            codes = daily.get("weathercode", [])
            code = codes[i] if i < len(codes) else -1
            condition, emoji = get_wmo_description(code)

            result_text += f"📅 **تاریخ:** {date_str}\n"
            result_text += f"وضعیت: {emoji} {condition}\n"
            result_text += f"دما: از {min_t}°C تا {max_t}°C\n"
            result_text += "➖➖➖➖➖➖➖\n"

        await cache_set(cache_key, result_text, ttl_sec=1800)
        return result_text

    except asyncio.TimeoutError:
        return "❌ ارتباط با سرور آب و هوا زمان‌بر شد."
    except Exception as e:
        print(f"Weather error: {e}")
        return "❌ خطایی در دریافت اطلاعات رخ داد."
