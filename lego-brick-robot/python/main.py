"""
main.py — Goalkeeper App entry point.

Captures frames, runs KeeperController (HSV detect + Kalman predict),
and drives a DoubleMotor to guard the goal:
  - ball found: slides (slowly, BALL_APPROACH_SPEED) to center on it, then
    holds still there. Moves again only if the ball's position changes.
  - ball not found: motor stays put -- no idle search motion. Constant
    left/right movement was feeding jitter back into detection/tracking.
  - clamped to +/-LIMIT (goal width); this is a lateral slider only, no
    forward/backward axis.
Also pushes a live annotated camera feed + status to the web_ui brick.

Motor access goes through the `lego` brick (bricks/lego/__init__.py), which
is an RPC proxy to the `lego-ble` sidecar container — the `main` container
has no Bluetooth/D-Bus access, so legoeducation/bleak can't run here directly.
`movement_move_tank` has no named wrapper on DoubleMotor, so it's invoked via
the brick's generic `call()` escape hatch, same as before.
"""

import base64
import time

import cv2

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera

from lego import DoubleMotor, LegoError

from keeper import KeeperController

# ---------------- config ----------------
DRY_RUN = False                  # True = never touch real motors, just print/log
MOTOR_COLOR = "green"
MOTOR_SERIAL = "0026"
MOTOR_SIGN = 1                   # flip if forward/back feels reversed
RIGHT_SIGN = -1                  # -1 = tank tilts in place; +1 = drives straight
BALL_APPROACH_SPEED = 8          # slow cap for leaning toward the ball
CAMERA_RESOLUTION = (1280, 720)
CAMERA_RGB = False                # True/False toggles RGB<->BGR swap fix

LIMIT = 200.0                    # max travel each side of center (goal width / 2)
KP_POS = 0.4                     # position-error -> speed gain (gentle)
KV = 0.4                         # cmd -> keeper position integration gain
POS_DEADBAND = 10.0              # raised for extra hysteresis against detection jitter
LOOKAHEAD = 4

CONNECT_ATTEMPTS = 5             # BLE connect retries (mirrors old lelib.py behavior)
CONNECT_RETRY_DELAY = 1.0        # seconds between attempts

# ---------------- globals ----------------
camera = None
motor = None
controller = None
ui = None
_keeper_pos = 0.0


def _connect_motor():
    """Retry connect() a few times -- BLE hubs can report 'not ready' on the
    first attempt or two right after power-on."""
    for attempt in range(CONNECT_ATTEMPTS):
        try:
            if motor.connect():
                return
        except LegoError as exc:
            if attempt == CONNECT_ATTEMPTS - 1:
                raise
            if "not ready" not in str(exc).lower():
                raise
        time.sleep(CONNECT_RETRY_DELAY)
    raise ConnectionError("Error connecting to Double Motor.")


def setup():
    global camera, motor, controller, ui

    ui = WebUI()

    camera = Camera(resolution=CAMERA_RESOLUTION)
    camera.start()

    controller = KeeperController(max_speed=BALL_APPROACH_SPEED, lookahead=LOOKAHEAD)

    if not DRY_RUN:
        motor = DoubleMotor(card_color=MOTOR_COLOR, card_serial=MOTOR_SERIAL)
        _connect_motor()
        print(f"[main] motor connected: color={MOTOR_COLOR} serial={MOTOR_SERIAL}")
    else:
        print("[main] DRY_RUN=True, motor not connected")


def drive(cmd):
    cmd = int(cmd) * MOTOR_SIGN
    if DRY_RUN or motor is None:
        return
    motor.call("movement_move_tank", cmd, cmd * RIGHT_SIGN)


def loop():
    global _keeper_pos

    frame = camera.capture()
    if frame is None:
        return
    if CAMERA_RGB:
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    r = controller.process(frame)

    if r.found:
        # Center on the ball's actual offset and hold -- once the ball stops
        # moving, target stops changing and cmd settles to 0 inside the
        # deadband instead of oscillating past it.
        target = max(-LIMIT, min(LIMIT, r.error))
        mode = "hold-on-ball"
        pdir = "right" if r.error > POS_DEADBAND else "left" if r.error < -POS_DEADBAND else "-"
    else:
        # No ball: stay exactly where we are. No idle search motion --
        # constant left/right movement was feeding jitter back into detection.
        target = _keeper_pos
        mode = "idle-still"
        pdir = "-"

    err = target - _keeper_pos
    cmd = 0 if abs(err) < POS_DEADBAND else int(max(-BALL_APPROACH_SPEED, min(BALL_APPROACH_SPEED, KP_POS * err)))
    _keeper_pos = max(-LIMIT, min(LIMIT, _keeper_pos + KV * cmd))
    drive(cmd)

    annotated = controller.draw(frame.copy(), r)
    ok, buf = cv2.imencode(".jpg", annotated)
    if ok:
        ui.send_message("frame", base64.b64encode(buf.tobytes()).decode("ascii"))

    ui.send_message("status", {
        "mode": mode,
        "found": r.found,
        "dir": pdir,
        "pos": round(_keeper_pos, 1),
        "cmd": cmd,
        "vx": round(r.vx, 2),
        "limit": LIMIT,
        "fps": 0.0,
    })


def main():
    setup()
    try:
        App.run(user_loop=loop)
    finally:
        if motor is not None:
            try:
                motor.call("movement_stop")
            except Exception:
                pass
            try:
                motor.disconnect()
            except Exception:
                pass
            print("[main] motor stopped and disconnected")


if __name__ == "__main__":
    main()
