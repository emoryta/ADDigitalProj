import time
import math
import array
import random

import board
import audiobusio
import neopixel

from digitalio import DigitalInOut, Pull
from adafruit_debouncer import Debouncer

# -------------------------
# Toggles / Constants
# -------------------------
DEBUG = True
FPS = 60              # Main loop rate target (approx)
BRIGHTNESS = 0.35     # Global brightness cap (safer on power)
AUTO_WRITE = False

PIN_LEFT = board.D5
PIN_RIGHT = board.D6
N_PER_SIDE = 5

BUTTON_PIN = board.D9

MIC_CLOCK = board.TX
MIC_DATA = board.D12
SAMPLE_RATE = 16000
SAMPLES = 320

# Audio smoothing (envelope follower)
ATTACK = 0.55   # faster rise = more reactive
RELEASE = 0.12  # faster fall = more motion

# Audio Sensitivity
MIC_GAIN = 21.0
ENV_MAX = 0.15   # envelope for normalization

# -------------------------
# Hardware setup
# -------------------------
pixels_left = neopixel.NeoPixel(PIN_LEFT, N_PER_SIDE, brightness=BRIGHTNESS, auto_write=AUTO_WRITE)
pixels_right = neopixel.NeoPixel(PIN_RIGHT, N_PER_SIDE, brightness=BRIGHTNESS, auto_write=AUTO_WRITE)

button_io = DigitalInOut(BUTTON_PIN)
button_io.pull = Pull.UP
button = Debouncer(button_io)

mic = audiobusio.PDMIn(MIC_CLOCK, MIC_DATA, sample_rate=SAMPLE_RATE, bit_depth=16)
samples = array.array("H", [0] * SAMPLES)

# -------------------------
# Helpers
# -------------------------
def dbg(*args):
    if DEBUG:
        print(*args)

def clamp01(x):
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x

def mean_u16(buf):
    s = 0
    for v in buf:
        s += v
    return s / len(buf)

def normalized_rms_u16(buf):
    # Remove DC bias and compute RMS, normalized to ~0..1
    m = int(mean_u16(buf))
    acc = 0
    for v in buf:
        d = v - m
        acc += d * d
    return math.sqrt(acc / len(buf)) / 65535.0

def apply_gamma(color, gamma=2.2):
    r, g, b = color
    r = int(((r / 255.0) ** gamma) * 255.0 + 0.5)
    g = int(((g / 255.0) ** gamma) * 255.0 + 0.5)
    b = int(((b / 255.0) ** gamma) * 255.0 + 0.5)
    return (r, g, b)

def hsv_to_rgb(h, s, v):
    h = h % 1.0
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i % 6

    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q

    return (int(r * 255), int(g * 255), int(b * 255))

def rainbow_soft_hot(h, v):
    h = h % 1.0

    s = 0.90

    d_red = min(abs(h - 0.0), abs(h - 1.0))
    d_orange = abs(h - 0.08)

    hot = 0.0
    if d_red < 0.10:
        hot = max(hot, (0.10 - d_red) / 0.10)
    if d_orange < 0.08:
        hot = max(hot, (0.08 - d_orange) / 0.08)

    s = s * (1.0 - 0.45 * hot)
    v2 = v * (1.0 - 0.25 * hot)

    c = hsv_to_rgb(h, s, v2)
    return apply_gamma(c, gamma=2.0)

def fill_all(color):
    pixels_left.fill(color)
    pixels_right.fill(color)

def show():
    pixels_left.show()
    pixels_right.show()

def clear_all():
    fill_all((0, 0, 0))
    show()

def set_u_index(i, color):
    # i is 0..(2*N_PER_SIDE-1) along the upside-down U
    # 0 is top-center LEFT[0], then LEFT goes down to LEFT[N-1],
    # then continue from RIGHT[N-1] up to RIGHT[0] (mirrored)
    n = N_PER_SIDE
    if i < n:
        pixels_left[i] = color
    else:
        j = (2 * n - 1) - i
        pixels_right[j] = color

def clear_u():
    for i in range(N_PER_SIDE):
        pixels_left[i] = (0, 0, 0)
        pixels_right[i] = (0, 0, 0)

def draw_bar(level, on_color=(80, 160, 255), off_color=(0, 0, 0)):
    for i in range(N_PER_SIDE):
        c = on_color if i < level else off_color
        pixels_left[i] = c
        pixels_right[i] = c

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_color(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)),
            int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))

# -------------------------
# Modes
# -------------------------
MODE_OFF = 0
MODE_STATIC = 1
MODE_RAINBOW_BREATHE = 2
MODE_SOUND_BAR = 3
MODE_SOUND_COLOR = 4
MODE_SOUND_SPARKLE = 5
MODE_RAINBOW_FLOW = 6  # NEW

MODE_NAMES = (
    "OFF",
    "STATIC",
    "RAINBOW_BREATHE",
    "SOUND_BAR",
    "SOUND_COLOR",
    "SOUND_SPARKLE",
    "RAINBOW_FLOW",      # NEW
)

mode = MODE_SOUND_BAR

PASTEL_RED = (255, 90, 110)

# Sound envelope state
env = 0.0

# Animation state
t0 = time.monotonic()
hue_base = 0.0
flow_phase = 0.0

dbg("Boot. Starting mode:", MODE_NAMES[mode])

# -------------------------
# Main loop
# -------------------------
while True:
    loop_start = time.monotonic()

    # Button update + mode switching
    button.update()
    if button.fell:
        mode = (mode + 1) % len(MODE_NAMES)
        dbg("Mode ->", MODE_NAMES[mode])
        clear_all()

    # Read audio
    mic.record(samples, len(samples))
    rms = normalized_rms_u16(samples) * MIC_GAIN

    # Envelope follower (smooth it)
    if rms > env:
        env = env + (rms - env) * ATTACK
    else:
        env = env + (rms - env) * RELEASE

    # Normalize envelope to 0..1 for consistent scaling everywhere
    env_n = clamp01(env / ENV_MAX)

    if DEBUG:
        dbg("rms", round(rms, 4), "env", round(env, 4), "n", round(env_n, 3), "mode", MODE_NAMES[mode])

    # Mode rendering
    now = time.monotonic()
    dt = now - t0
    t0 = now

    if mode == MODE_OFF:
        clear_u()
        show()

    elif mode == MODE_STATIC:
        fill_all(PASTEL_RED)
        show()

    elif mode == MODE_RAINBOW_BREATHE:
        # Breathing brightness + traveling rainbow across the U
        hue_base = (hue_base + dt * 0.08) % 1.0  # slow drift
        breathe = 0.30 + 0.70 * (0.5 + 0.5 * math.sin(now * 2.0))  # 0.30..1.0

        clear_u()
        total = 2 * N_PER_SIDE
        for i in range(total):
            h = hue_base + (i / total) * 0.65
            c = rainbow_soft_hot(h, breathe)
            set_u_index(i, c)
        show()

    elif mode == MODE_RAINBOW_FLOW:
        # Speed
        flow_phase = (flow_phase + dt * 0.25) % 1.0  # cycles/second (increase for faster)

        # Brightness knob:
        v = 0.55  # keep this moderate so it's not harsh

        total = 2 * N_PER_SIDE
        clear_u()

        # Each pixel has a hue offset; phase pushes the pattern forward around the U.
        for i in range(total):
            # Move forward along the U: increasing phase makes the whole rainbow advance.
            h = (flow_phase + (i / total)) % 1.0
            c = rainbow_soft_hot(h, v)
            set_u_index(i, c)

        show()

    elif mode == MODE_SOUND_BAR:
        level = int(env_n * N_PER_SIDE + 0.5)
        if level > N_PER_SIDE:
            level = N_PER_SIDE

        c_low = (30, 200, 120)
        c_high = (255, 80, 30)
        t = level / float(N_PER_SIDE) if N_PER_SIDE else 0.0
        on_color = lerp_color(c_low, c_high, t)

        draw_bar(level, on_color=on_color, off_color=(0, 0, 0))
        show()

    elif mode == MODE_SOUND_COLOR:
        loud = env_n
        hue = lerp(0.70, 0.02, loud)
        val = 0.25 + 0.75 * loud
        c = hsv_to_rgb(hue, 1.0, val)

        fill_all(c)
        show()

    elif mode == MODE_SOUND_SPARKLE:
        loud = env_n
        base = hsv_to_rgb(0.58, 1.0, 0.18 + 0.20 * loud)
        sparkle = hsv_to_rgb(0.10, 0.3, 1.0)

        fill_all(base)

        sparks = int(loud * 6.0 + 0.2)
        total = 2 * N_PER_SIDE
        for _ in range(sparks):
            idx = random.randrange(total)
            set_u_index(idx, sparkle)

        show()

    # Frame pacing
    target_dt = 1.0 / FPS
    elapsed = time.monotonic() - loop_start
    if elapsed < target_dt:
        time.sleep(target_dt - elapsed)
