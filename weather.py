# weather.py
import requests

def get_wmo_description(code):
    # (کدهای آب و هوا - مشابه کد قبلی شما)
    weather_codes = {
        0: ("صاف و آفتابی", "☀️"),
        1: ("عمدتاً صاف", "🌤"),
        2: ("نیمه ابری", "⛅️"),
        3: ("ابری", "☁️"),
        45: ("مه‌آلود", "🌫"),
        48: ("مه همراه با یخ‌زدگی", "❄️🌫"),
        51: ("نم‌نم باران (سبک)", "🌦"),
        53: ("نم‌نم باران (متوسط)", "🌧"),
        55: ("نم‌نم باران (شدید)", "🌧"),
        61: ("بارانی (سبک)", "☔️"),
        63: ("بارانی (متوسط)", "🌧"),
        65: ("بارانی (شدید)", "⛈"),
        71: ("برفی (سبک)", "🌨"),
        73: ("برفی (متوسط)", "❄️"),
        75: ("برفی (شدید)", "☃️"),
        95: ("رعد و برق", "🌩"),
        96: ("رعد و برق با تگرگ (سبک)", "⛈❄️"),
        99: ("رعد و برق با تگرگ (شدید)", "⛈❄️")
    }
    return weather_codes.get(code, ("نامشخص", "🌍"))

def get_weather_forecast(city_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=en&format=json"
        geo_resp = requests.get(geo_url, timeout=10).json()

        if "results" not in geo_resp or not geo_resp["results"]:
            return f"❌ شهری با نام `{city_name}` پیدا نشد.\nلطفاً املای شهر را بررسی کنید (بهتر است نام شهر را به انگلیسی وارد کنید)."

        location = geo_resp["results"][0]
        lat = location["latitude"]
        lon = location["longitude"]
        country = location.get("country", "نامشخص")
        city = location["name"]

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=3"
        weather_resp = requests.get(weather_url, timeout=10).json()

        daily = weather_resp.get("daily", {})
        times = daily.get("time", [])
        max_temps = daily.get("temperature_2m_max", [])
        min_temps = daily.get("temperature_2m_min", [])
        codes = daily.get("weathercode", [])

        result_text = f"🌍 **پیش‌بینی آب و هوای {city}** ({country})\n\n"

        for i in range(len(times)):
            date_str = times[i]
            max_t = max_temps[i]
            min_t = min_temps[i]
            code = codes[i]
            condition, emoji = get_wmo_description(code)

            result_text += f"📅 **تاریخ:** {date_str}\n"
            result_text += f"وضعیت: {emoji} {condition}\n"
            result_text += f"دما: از $ {min_t}^{{\\circ}}C $ تا $ {max_t}^{{\\circ}}C $\n"
            result_text += "➖➖➖➖➖➖➖\n"

        return result_text

    except Exception as e:
        return f"❌ خطایی در دریافت اطلاعات رخ داد:\n`{str(e)}`"
