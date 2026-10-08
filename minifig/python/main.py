"""UNO Q Linux side: subscribe to one minifig color, decide how to drive, tell the MCU.

POLICY (proportional control with a deadband):
    error = TARGET_X - x            (x = minifig position, 0 = left edge, 1 = right edge)
    |error| < DEADBAND              -> stop (we've arrived)
    otherwise                       -> speed = KP * error, clamped to [MIN_SPEED, MAX_SPEED]
                                       (far away = faster, close = slower, sign = direction)
    no detection / no message for TIMEOUT_S -> stop and blank the LED matrix (fail safe)
"""
import json
import threading
import time

import paho.mqtt.client as mqtt
from arduino.app_utils import App, Bridge

# ---- per-car settings -------------------------------------------------------
BROKER = "broker.hivemq.com"
PORT = 1883
GROUP = "group1"
COLOR = "green"        # "green" car or "blue" car
TARGET_X = 0.5         # 0.5 = middle of the screen; e.g. 0.25 for left, 0.75 for right
INVERT = False         # flip if the car drives away from its target

KP = 600               # speed per unit of error (error is at most 1.0)
DEADBAND = 0.04        # "close enough" band around the target, as a fraction of image width
MIN_SPEED = 90         # PWM below this usually won't move the car
MAX_SPEED = 200        # PWM 0-255
TIMEOUT_S = 0.5        # stop if the laptop goes quiet this long

ROWS, COLS = 8, 13     # UNO Q LED matrix
# -----------------------------------------------------------------------------

TOPIC = f"me193/{GROUP}/minifig/{COLOR}"
latest = {"msg": None, "time": 0.0}
lock = threading.Lock()


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"MQTT connected ({reason_code}), subscribing to {TOPIC}")
    client.subscribe(TOPIC)


def on_message(client, userdata, message):
    try:
        msg = json.loads(message.payload)
    except ValueError:
        return
    with lock:
        latest["msg"] = msg
        latest["time"] = time.time()


def policy(x):
    """Minifig x position (0-1) -> signed motor speed (-255..255)."""
    error = TARGET_X - x
    if abs(error) < DEADBAND:
        return 0
    speed = max(MIN_SPEED, min(MAX_SPEED, KP * abs(error)))
    speed = speed if error > 0 else -speed
    return -speed if INVERT else speed


def loop():
    with lock:
        msg, stamp = latest["msg"], latest["time"]

    seen = msg is not None and msg.get("detected") and time.time() - stamp < TIMEOUT_S
    if seen:
        col = min(COLS - 1, max(0, round(msg["x"] * (COLS - 1))))
        row = min(ROWS - 1, max(0, round(msg["y"] * (ROWS - 1))))
        speed = int(policy(msg["x"]))
    else:
        col = row = -1     # blank the display
        speed = 0

    Bridge.call("show_dot", col, row)
    Bridge.call("drive", speed)   # sent every loop so the MCU watchdog stays fed
    time.sleep(0.05)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT)
client.loop_start()

App.run(user_loop=loop)
