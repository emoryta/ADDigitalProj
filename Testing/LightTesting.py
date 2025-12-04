import time
import board
import neopixel

# --- CONFIG ---
NUM_PIXELS = 5
BRIGHTNESS = 0.3

# NeoPixel objects
pixels_5 = neopixel.NeoPixel(board.D5, NUM_PIXELS, brightness=BRIGHTNESS, auto_write=False)
pixels_6 = neopixel.NeoPixel(board.D6, NUM_PIXELS, brightness=BRIGHTNESS, auto_write=False)

# Colors to cycle through (R, G, B)
COLORS = [
    (255,   0,   0),   # Red
    (0,   255,   0),   # Green
    (0,     0, 255),   # Blue
    (255, 255,   0),   # Yellow
    (0,   255, 255),   # Cyan
    (255,   0, 255),   # Magenta
    (255, 255, 255),   # White
]

def blink_all(color, delay=0.2):
    """Blink both pixel groups together."""
    pixels_5.fill(color)
    pixels_6.fill(color)
    pixels_5.show()
    pixels_6.show()
    time.sleep(delay)

    pixels_5.fill((0, 0, 0))
    pixels_6.fill((0, 0, 0))
    pixels_5.show()
    pixels_6.show()
    time.sleep(delay)

def cycle_strips(delay=0.1):
    """Chase through the strips one pixel at a time."""
    for i in range(NUM_PIXELS):
        # Clear first
        pixels_5.fill((0, 0, 0))
        pixels_6.fill((0, 0, 0))

        # Light a single pixel
        pixels_5[i] = (0, 100, 255)
        pixels_6[i] = (255, 50, 0)

        pixels_5.show()
        pixels_6.show()

        time.sleep(delay)


while True:
    # Blink major colors
    for c in COLORS:
        blink_all(c, delay=0.15)

    # Run a quick chase on each strip
    cycle_strips(0.1)
