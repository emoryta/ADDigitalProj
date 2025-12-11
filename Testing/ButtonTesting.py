import board
import digitalio
import time

# Button on D9
button = digitalio.DigitalInOut(board.D9)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP  # internal pull-up

last_state = button.value

print("Button test ready. Press the button.")

while True:
    current_state = button.value

    # Detect state change
    if current_state != last_state:
        if not current_state:
            print("PRESSED")
        else:
            print("RELEASED")

        last_state = current_state

    time.sleep(0.01)  # simple debounce
