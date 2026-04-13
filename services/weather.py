# services/weather.py

import requests

def get_wmo_description(code):
    weather_codes = {
        0: ("صاف و آفتابی", "☀️"), 1: ("عمدتاً صاف", "🌤"), 2: ("نیمه ابری", "⛅️"),
        3: ("ابری", "☁️"), 45: ("مه‌آلود", "🌫"), 48: ("مه همراه با یخ‌زدگی", "❄️🌫"),
        51: ("نم‌نم باران", "🌦"), 61: ("بارانی", "☔️"), 71: ("برفی", "🌨"),
        95: ("رعد و برق", "🌩")
    }
    return weather_codes.get(code, ("نامشخص", "🌍"))

def get_weather_forecast(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=en&format=json"
        geo_resp = requests.get(geo_url, timeout=10).json()

        if "results" not in geo_resp or not geo_resp["results"]:
            return f"❌ شهری با نام `{city_name}` پیدا نشد."

        location = geo_resp["results"][0]
        lat, lon = location["latitude"], location["longitude"]
        city, country = location["name"], location.get("country", "نامشخص")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=3"
        weather_resp = requests.get(weather_url, timeout=10).json()

        daily = weather_resp.get("daily", {})
        result_text = f"🌍 **پیش‌بینی آب و هوای {city}** ({country})\n\n"

        for i in range(len(daily.get("time", []))):
            date_str = daily["time"][i]
            max_t = daily["temperature_2m_max"][i]
            min_t = daily["temperature_2m_min"][i]
            condition, emoji = get_wmo_description(daily["weathercode"][i])

            result_text += f"📅 **تاریخ:** {date_str}\n"
            result_text += f"وضعیت: {emoji} {condition}\n"
            result_text += f"دما: از $ {min_t}^{{\\circ}}C $ تا $ {max_t}^{{\\circ}}C $\n"
            result_text += "➖➖➖➖➖➖➖\n"

        return result_text
    except Exception as e:
        return f"❌ خطایی در دریافت اطلاعات رخ داد."
