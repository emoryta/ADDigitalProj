# code.py — Feather ESP32-S3 TFT + CircuitPython 9.x
import time, ssl, wifi, socketpool, board
import adafruit_requests
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import bitmap_label

# ----- CONFIG -----
LAT, LON = 47.2529, -122.4443
UNITS = "imperial"  # or "metric"
FONT_PATH = "/fonts/cjk16.bdf"
TEXT_COLOR = 0xFF0000
UPDATE_SECS = 30

CITY_MAP = {
    "San Francisco": "旧金山",
    "Daly City": "戴利城",
}

# Map common OpenWeather "description" (lowercase) to Chinese
COND_MAP = {
    "clear sky": "晴",
    "few clouds": "多云",
    "scattered clouds": "多云",
    "broken clouds": "多云",
    "overcast clouds": "阴",
    "mist": "雾",
    "smoke": "烟",
    "haze": "霾",
    "dust": "扬尘",
    "fog": "雾",
    "sand": "沙尘",
    "ash": "灰",
    "squalls": "阵风",
    "tornado": "龙卷风",
    "light rain": "小雨",
    "moderate rain": "中雨",
    "heavy intensity rain": "大雨",
    "very heavy rain": "暴雨",
    "extreme rain": "特大暴雨",
    "freezing rain": "冻雨",
    "light intensity shower rain": "小阵雨",
    "shower rain": "阵雨",
    "heavy intensity shower rain": "大阵雨",
    "ragged shower rain": "阵雨",
    "thunderstorm": "雷雨",
    "thunderstorm with light rain": "雷阵雨",
    "thunderstorm with rain": "雷阵雨",
    "thunderstorm with heavy rain": "强雷阵雨",
    "light thunderstorm": "雷雨",
    "heavy thunderstorm": "强雷雨",
    "ragged thunderstorm": "雷雨",
    "light snow": "小雪",
    "snow": "雪",
    "heavy snow": "大雪",
    "sleet": "雨夹雪",
    "light shower sleet": "小阵雪",
    "shower sleet": "阵雪",
    "light rain and snow": "小雨夹雪",
    "rain and snow": "雨夹雪",
    "light shower snow": "小阵雪",
    "shower snow": "阵雪",
    "heavy shower snow": "大阵雪",
    "drizzle": "小雨",
    "light intensity drizzle": "小雨",
    "heavy intensity drizzle": "大雨",
    "drizzle rain": "小雨",
    "heavy intensity drizzle rain": "大雨",
    "shower drizzle": "阵雨",
}

def cn_or_en_city(name: str) -> str:
    return CITY_MAP.get(name, name or "")

def cn_or_en_cond(desc_en: str, have_ascii: bool = True) -> str:
    if not desc_en:
        return ""
    cn = COND_MAP.get(desc_en.lower().strip())
    # If we have a Chinese mapping, use it; else fall back to English (ASCII is in your subset now)
    return cn if cn else desc_en

# ----- SECRETS -----
try:
    from secrets import secrets
    SSID = secrets["ssid"]; PASS = secrets["password"]; OWM_KEY = secrets["owm_api_key"]
except KeyError as e:
    raise RuntimeError(f"secrets.py missing: {e}")

URL = (
    "https://api.openweathermap.org/data/2.5/weather"
    f"?lat={LAT}&lon={LON}&units={UNITS}&appid={OWM_KEY}"
)

# ----- WIFI/HTTP -----
print("Connecting Wi-Fi…")
wifi.radio.connect(SSID, PASS)
print("Connected to", SSID)
print("IP:", wifi.radio.ipv4_address)

pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

# ----- FONT/LABEL -----
font = bitmap_font.load_font(FONT_PATH)

# Make sure your BDF includes these chars (ASCII + degree + Chinese you use)
needed = (
    "现在在是温度度华氏摄氏天气晴多云小雨中雨大雨阵雨雾阴雷雪霾扬尘龙卷风雨夹雪阵风旧金山戴利城"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789:% .°F℃()/–-,:;!?"
)
font.load_glyphs([ord(c) for c in needed])

label = bitmap_label.Label(font, text="", scale=1, color=TEXT_COLOR)
label.x = 10
label.y = 20  # a bit higher to fit 3 lines
board.DISPLAY.root_group = label

def deg(temp):
    t = int(round(temp))
    return f"{t}°F" if UNITS == "imperial" else f"{t}°C"

def make_text(temp, city_en, cond_en):
    city = cn_or_en_city(city_en)
    cond = cn_or_en_cond(cond_en)
    # 3 lines: city, temperature, condition
    return f"现在{city}是\n{deg(temp)}\n{cond}"

while True:
    try:
        r = requests.get(URL)
        d = r.json()
        temp = d["main"]["temp"]
        city = d.get("name", "")
        cond_en = ""
        w = d.get("weather")
        if isinstance(w, list) and w:
            cond_en = w[0].get("description", "") or w[0].get("main", "")
        label.text = make_text(temp, city, cond_en)
    except Exception as e:
        # Keep error ASCII so it always renders
        label.text = f"Error:\n{e}"
    time.sleep(UPDATE_SECS)
