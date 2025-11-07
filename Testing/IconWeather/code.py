import time, ssl, wifi, socketpool, adafruit_requests
import board, displayio, terminalio
from adafruit_display_text import bitmap_label

# ---------------- CONFIG ----------------
LAT = 37.7195
LON = -122.4411
UNITS = "imperial"
APPID = "API" #API KEY HERE
ICON_DIR = "/icons"
POLL_SECONDS = 60

# Colors
BG = 0x101218
CARD = 0x181B22
TEXT_MAIN = 0xFFFFFF
TEXT_DIM = 0xA9B1C6

# ---------------- WIFI ------------------
from secrets import secrets
wifi.radio.connect(secrets["ssid"], secrets["password"])
pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

# ---------------- DISPLAY ----------------
display = board.DISPLAY
W, H = display.width, display.height
display.auto_refresh = True
root = displayio.Group()
display.root_group = root

MARGIN = 6
HEADER_H = 20

def rect(x, y, w, h, color):
    bmp = displayio.Bitmap(w, h, 1)
    pal = displayio.Palette(1); pal[0] = color
    return displayio.TileGrid(bmp, pixel_shader=pal, x=x, y=y)

root.append(rect(0, 0, W, H, BG))
root.append(rect(0, 0, W, HEADER_H, CARD))

title = bitmap_label.Label(terminalio.FONT, text="Weather", color=TEXT_MAIN, scale=1,
                           anchor_point=(0, 0.5), anchored_position=(MARGIN, HEADER_H//2))
updated = bitmap_label.Label(terminalio.FONT, text="", color=TEXT_DIM, scale=1,
                             anchor_point=(1, 0.5), anchored_position=(W - MARGIN, HEADER_H//2))
root.append(title); root.append(updated)

temp_lbl = bitmap_label.Label(terminalio.FONT, text="--", color=TEXT_MAIN, scale=3,
                              anchor_point=(1, 0), anchored_position=(W - MARGIN, HEADER_H + MARGIN))
cond_lbl = bitmap_label.Label(terminalio.FONT, text="--", color=TEXT_DIM, scale=1,
                              anchor_point=(0.5, 1), anchored_position=(W/2, H - MARGIN))
root.append(temp_lbl); root.append(cond_lbl)

icon_tg = None
def remove_icon():
    global icon_tg
    if icon_tg and icon_tg in root:
        root.remove(icon_tg)
    icon_tg = None

def load_scaled_icon(name):
    global icon_tg
    try:
        bmp = displayio.OnDiskBitmap(f"{ICON_DIR}/{name}")
    except Exception as e:
        print("Icon load failed:", e); return

    top = HEADER_H + MARGIN
    bottom = int(cond_lbl.anchored_position[1]) - MARGIN
    avail_h = max(8, bottom - top)
    avail_w = max(8, int(W * 0.45) - 2*MARGIN)

    iw, ih = bmp.width, bmp.height
    if iw < 1 or ih < 1:
        return
    sx = max(1, min(avail_w // iw, avail_h // ih))
    sx = max(1, min(sx, 4))

    box_w = iw * sx
    box_h = ih * sx
    x = MARGIN + (avail_w - box_w) // 2
    y = top + (avail_h - box_h) // 2

    icon_tg = displayio.TileGrid(bmp, pixel_shader=bmp.pixel_shader, x=int(x), y=int(y))
    try:
        icon_tg.scale = sx
    except Exception:
        pass

    root.insert(1, icon_tg)

def icon_for(code, tag):
    if code == 781: return "tornado.bmp"
    if 200 <= code <= 232: return "cloud.bolt.rain.fill.bmp"
    if 300 <= code <= 321: return "cloud.drizzle.fill.bmp"
    if 500 <= code <= 531:
        return "cloud.heavyrain.fill.bmp" if code >= 520 or code >= 502 else "cloud.fill.bmp"
    if 600 <= code <= 622: return "cloud.snow.fill.bmp"
    if 700 <= code <= 771: return "cloud.fog.fill.bmp"
    if code == 800: return "sun.max.fill.bmp" if str(tag).endswith("d") else "moon.stars.fill.bmp"
    if 801 <= code <= 804: return "cloud.fill.bmp"
    return "cloud.fill.bmp"

# ---------------- HELPERS ----------------
def t_ascii(t):
    if t is None: return "--"
    return str(int(round(t))) + ("C" if UNITS == "metric" else "F")

def nice_case(s):
    if not s: return ""
    s = str(s)
    parts = s.replace("_", " ").replace("-", " ").split()
    return " ".join(p[:1].upper() + p[1:] for p in parts)

def fetch_weather():
    url = ("https://api.openweathermap.org/data/2.5/weather"
           + "?lat=" + str(LAT)
           + "&lon=" + str(LON)
           + "&units=" + UNITS
           + "&appid=" + APPID)
    r = requests.get(url, timeout=10)
    if hasattr(r, "status_code") and r.status_code != 200:
        print("HTTP", r.status_code)
        try: print("Body:", r.text)
        except: pass
        return None
    try:
        return r.json()
    except Exception as e:
        print("JSON parse error:", e)
        return None

def autosize_temp():
    right_col_left = int(W * 0.52)
    avail = max(30, (W - MARGIN) - right_col_left)
    txt = temp_lbl.text if temp_lbl.text else "88F"
    per_char = 6
    for s in (4, 3, 2, 1):
        if len(txt) * per_char * s <= avail:
            temp_lbl.scale = s
            temp_lbl.anchored_position = (W - MARGIN, HEADER_H + MARGIN)
            break

def update_ui(data):
    name = data.get("name", "Weather")
    main = data.get("main", {})
    wlist = data.get("weather", [])
    if wlist:
        w0 = wlist[0]
        code = w0.get("id", 800)
        desc = nice_case(w0.get("description") or "clear")
        tag = w0.get("icon", "01d")
    else:
        code, desc, tag = 800, "Clear", "01d"

    title.text = name
    temp_lbl.text = t_ascii(main.get("temp"))
    autosize_temp()
    feels = main.get("feels_like")
    cond_text = desc + ("" if feels is None else " · Feels " + t_ascii(feels))
    cond_lbl.text = cond_text[:40]
    updated.text = "Updated"

    remove_icon()
    load_scaled_icon(icon_for(code, tag))

def show_error(msg):
    remove_icon()
    title.text = "Weather"
    temp_lbl.text = "--"
    cond_lbl.text = msg
    updated.text = ""

# ---------------- LOOP ----------------
while True:
    try:
        data = fetch_weather()
        if data and int(str(data.get("cod", "200"))) == 200:
            update_ui(data)
        else:
            show_error("API error")
    except Exception as e:
        print("Update failed:", e)
        show_error("Network")
    time.sleep(POLL_SECONDS)