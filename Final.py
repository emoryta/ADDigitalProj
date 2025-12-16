# Mic: PDM data on D12, clock on TX
# NeoPixels: 5 on D5 (left side), 5 on D6 (right side)
# Button: momentary on D9 to GND

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
# Toggles / constants
# -------------------------
DEBUG = True          # Toggle console output here
FPS = 60              # Main loop rate target (approx)
BRIGHTNESS = 0.35
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

# --- Audio sensitivity knobs ---
MIC_GAIN = 21.0  # baseline mic gain; auto-gain rides on top of this
ENV_MAX = 0.15   # "full-scale" envelope for normalization

# Adaptive loudness (automatic sensitivity) and transient tracking
AUTO_GAIN = True
AUTO_GAIN_TARGET = 0.48  # normalized envelope we aim to hover around
AUTO_GAIN_RISE = 0.10    # how fast gain rises when it's too quiet
AUTO_GAIN_FALL = 0.04    # how fast gain falls when it's too loud
AUTO_GAIN_MIN = 0.08
AUTO_GAIN_MAX = 5.0

SLOW_ENV_ATTACK = 0.02   # slow follower: reacts to overall song energy
SLOW_ENV_RELEASE = 0.003
PUNCH_BOOST = 3.5        # how much louder-than-baseline counts as a "hit"
BAR_PEAK_FALL = 0.015    # speed of the peak marker in the bar mode

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

def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
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
    """
    h: 0..1 hue
    v: 0..1 base brightness
    Softens reds/oranges so they don't look stark.
    """
    h = h % 1.0

    # Base rainbow: slightly less than full saturation already
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
MODE_RAINBOW_FLOW = 6
MODE_SOUND_PULSE = 7

MODE_NAMES = (
    "OFF",
    "STATIC",
    "RAINBOW_BREATHE",
    "SOUND_BAR",
    "SOUND_COLOR",
    "SOUND_SPARKLE",
    "RAINBOW_FLOW",
    "SOUND_PULSE",
)

mode = MODE_SOUND_BAR

PASTEL_RED = (255, 90, 110)

# Sound envelope state
env = 0.0
slow_env = 0.0
auto_gain = 1.0
bar_peak = 0.0

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
    rms = normalized_rms_u16(samples) * MIC_GAIN * auto_gain

    # Envelope follower (smooth it)
    if rms > env:
        env = env + (rms - env) * ATTACK
    else:
        env = env + (rms - env) * RELEASE

    # Normalize envelope to 0..1 for consistent scaling everywhere
    env_n = clamp01(env / ENV_MAX)

    # Adaptive gain: keep the normalized envelope hovering near AUTO_GAIN_TARGET
    if AUTO_GAIN:
        target = AUTO_GAIN_TARGET
        if env_n < target * 0.7:
            auto_gain += AUTO_GAIN_RISE * (target - env_n)
        elif env_n > target * 1.3:
            auto_gain -= AUTO_GAIN_FALL * (env_n - target)
        auto_gain = clamp(auto_gain, AUTO_GAIN_MIN, AUTO_GAIN_MAX)

    # Slow baseline + transient punch (beats) that don't care about absolute volume
    if env > slow_env:
        slow_env = slow_env + (env - slow_env) * SLOW_ENV_ATTACK
    else:
        slow_env = slow_env + (env - slow_env) * SLOW_ENV_RELEASE
    slow_env_n = clamp01(slow_env / ENV_MAX)
    punch = clamp01((env_n - slow_env_n) * PUNCH_BOOST)

    if DEBUG:
        dbg("r", round(rms, 4), "n", round(env_n, 3), "p", round(punch, 3), "g", round(auto_gain, 2), "m", MODE_NAMES[mode])

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
        flow_speed = 0.18 + 0.55 * env_n + 0.75 * punch
        flow_phase = (flow_phase + dt * flow_speed) % 1.0

        # Brightness leans on the adaptive loudness
        v = clamp01(0.18 + 0.55 * env_n + 0.35 * punch)

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

        # Peak marker (slowly falls so you can see the last hit)
        if env_n > bar_peak:
            bar_peak = env_n
        else:
            bar_peak = max(0.0, bar_peak - BAR_PEAK_FALL)

        total = N_PER_SIDE
        brightness = 0.35 + 0.65 * env_n

        for i in range(total):
            pos_t = i / float(total - 1 if total > 1 else 1)
            # Warm up toward the bottom + react to transients
            cool = (40, 160, 255)
            warm = (255, 110, 30)
            warm_mix = clamp01(pos_t * 0.75 + punch * 0.5)
            base_color = lerp_color(cool, warm, warm_mix)
            if i < level:
                c = (int(base_color[0] * brightness),
                     int(base_color[1] * brightness),
                     int(base_color[2] * brightness))
            else:
                c = (0, 0, 0)
            pixels_left[i] = c
            pixels_right[i] = c

        peak_idx = int(bar_peak * N_PER_SIDE + 0.2)
        if peak_idx >= N_PER_SIDE:
            peak_idx = N_PER_SIDE - 1
        if peak_idx >= 0:
            peak_color = (255, 255, 255) if bar_peak > 0.05 else (0, 0, 0)
            pixels_left[peak_idx] = peak_color
            pixels_right[peak_idx] = peak_color
        show()

    elif mode == MODE_SOUND_COLOR:
        loud = env_n
        hue = lerp(0.70, 0.02, loud)
        val = 0.25 + 0.75 * loud
        c = hsv_to_rgb(hue, 1.0, val)

        # Add a soft white flash on hits so it pops without being blinding
        if punch > 0.05:
            flash = clamp01(punch * 0.9)
            c = lerp_color(c, (255, 255, 255), flash)

        fill_all(c)
        show()

    elif mode == MODE_SOUND_SPARKLE:
        loud = env_n
        base = hsv_to_rgb(0.58, 0.9, 0.18 + 0.30 * loud + 0.25 * punch)
        sparkle = hsv_to_rgb(0.10 + 0.12 * punch, 0.4, 1.0)

        fill_all(base)

        sparks = int(loud * 6.0 + punch * 8.0 + 0.4)
        total = 2 * N_PER_SIDE
        for _ in range(sparks):
            idx = random.randrange(total)
            set_u_index(idx, sparkle)

        show()

    elif mode == MODE_SOUND_PULSE:
        # Uniform pulse for reflections; rides on adaptive loudness + hits
        brightness = clamp01(0.05 + 0.80 * env_n + 0.45 * punch)
        warm_white = (255, 220, 180)
        c = (int(warm_white[0] * brightness),
             int(warm_white[1] * brightness),
             int(warm_white[2] * brightness))
        fill_all(c)
        show()

    # Frame pacing
    target_dt = 1.0 / FPS
    elapsed = time.monotonic() - loop_start
    if elapsed < target_dt:
        time.sleep(target_dt - elapsed)
