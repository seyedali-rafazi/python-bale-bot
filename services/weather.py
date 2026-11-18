# services/weather.py

import aiohttp
import asyncio
import logging
import urllib.parse
from services.http_client import get_http_session

logger = logging.getLogger(__name__)


_inflight_weather: dict[str, asyncio.Future] = {}


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


async def _fetch_weather_uncached(clean_name: str, cache_key: str) -> str:
    timeout = aiohttp.ClientTimeout(total=15)
    session = await get_http_session()

    is_farsi = any(ord(c) > 127 for c in clean_name)
    primary_lang, fallback_lang = ("fa", "en") if is_farsi else ("en", "fa")
    encoded_name = urllib.parse.quote(clean_name)

    async def _geocode(lang: str):
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_name}&count=1&language={lang}&format=json"
        async with session.get(geo_url, timeout=timeout) as geo_resp:
            if geo_resp.status == 200:
                geo_data = await geo_resp.json()
                results = geo_data.get("results")
                if results:
                    return results[0]
        return None

    location = await _geocode(primary_lang)
    if not location:
        location = await _geocode(fallback_lang)

    if not location:
        return f"❌ شهری با نام `{clean_name}` پیدا نشد."

    lat, lon = location["latitude"], location["longitude"]
    city = location.get("name", clean_name)
    country = location.get("country", "نامشخص")

    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=3"
    )
    async with session.get(weather_url, timeout=timeout) as weather_resp:
        if weather_resp.status != 200:
            return "❌ خطایی در دریافت اطلاعات آب و هوا رخ داد."
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

    from services.cache_service import cache_set

    await cache_set(cache_key, result_text, ttl_sec=1800)
    return result_text


async def get_weather_forecast(city_name: str) -> str:
    try:
        clean_name = city_name.strip()
        if not clean_name:
            return "❌ لطفاً نام شهر را وارد کنید."

        from services.cache_service import cache_get
        cache_key = f"weather:{clean_name.lower()}"
        cached_forecast = await cache_get(cache_key)
        if cached_forecast:
            return cached_forecast

        existing = _inflight_weather.get(cache_key)
        if existing is not None and not existing.done():
            return await asyncio.shield(existing)

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        _inflight_weather[cache_key] = fut
        try:
            res = await _fetch_weather_uncached(clean_name, cache_key)
            if not fut.done():
                fut.set_result(res)
            return res
        except asyncio.CancelledError:
            if not fut.done():
                fut.cancel()
            raise
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
                fut.exception()
            raise
        finally:
            if _inflight_weather.get(cache_key) is fut:
                _inflight_weather.pop(cache_key, None)

    except asyncio.TimeoutError:
        return "❌ ارتباط با سرور آب و هوا زمان‌بر شد."
    except Exception as e:
        logger.warning("Weather error: %s", e)
        return "❌ خطایی در دریافت اطلاعات رخ داد."
