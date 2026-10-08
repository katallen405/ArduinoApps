"""
main.py — Goalkeeper App entry point.

Captures frames, runs KeeperController (HSV detect + Kalman predict),
and drives a DoubleMotor to guard the goal:
  - idle: wiggles back and forth around center
  - ball's predicted horizontal velocity crosses VX_THRESH: nudges toward
    that side, clamped to +/-LIMIT (goal width) — never chases forward.
Also pushes a live annotated camera feed + status to the web_ui brick.
"""

import base64
import math

import cv2

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera

from keeper import KeeperController
import lelib as le

# ---------------- config ----------------
DRY_RUN = False                  # True = never touch real motors, just print/log
MOTOR_COLOR = "green"
MOTOR_SERIAL = "0026"
MOTOR_SIGN = 1                   # flip if forward/back feels reversed
RIGHT_SIGN = -1                  # -1 = tank tilts in place; +1 = drives straight
MAX_SPEED = 60
CAMERA_RESOLUTION = (1280, 720)
CAMERA_RGB = False                # True/False toggles RGB<->BGR swap fix

LIMIT = 200.0                    # max travel each side of center (goal width / 2)
NUDGE = 120.0                    # target offset when a direction is predicted
WIGGLE_AMP = 45.0                # idle wiggle amplitude (px-equivalent)
WIGGLE_PERIOD = 90               # frames per full wiggle cycle
VX_THRESH = 1.5                  # ball px/frame velocity needed to react
KP_POS = 0.6                     # position-error -> speed gain
KV = 0.4                         # cmd -> keeper position integration gain
POS_DEADBAND = 5.0
LOOKAHEAD = 4

# ---------------- globals ----------------
camera = None
motor = None
controller = None
ui = None
_keeper_pos = 0.0
_frame_i = 0


def setup():
    global camera, motor, controller, ui

    ui = WebUI()

    camera = Camera(resolution=CAMERA_RESOLUTION)
    camera.start()

    controller = KeeperController(max_speed=MAX_SPEED, lookahead=LOOKAHEAD)

    if not DRY_RUN:
        motor = le.doubleMotor()
        motor.connect(card_color=MOTOR_COLOR, card_serial=MOTOR_SERIAL)
        print(f"[main] motor connected: color={MOTOR_COLOR} serial={MOTOR_SERIAL}")
    else:
        print("[main] DRY_RUN=True, motor not connected")


def drive(cmd):
    cmd = int(cmd) * MOTOR_SIGN
    if DRY_RUN or motor is None:
        return
    motor.movement_move_tank(cmd, cmd * RIGHT_SIGN)


def loop():
    global _keeper_pos, _frame_i

    frame = camera.capture()
    if frame is None:
        return
    if CAMERA_RGB:
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    r = controller.process(frame)

    if r.found and abs(r.vx) > VX_THRESH:
        target = max(-LIMIT, min(LIMIT, math.copysign(NUDGE, r.vx)))
        mode = "track-right" if r.vx > 0 else "track-left"
        pdir = "right" if r.vx > 0 else "left"
    else:
        phase = (_frame_i % WIGGLE_PERIOD) / WIGGLE_PERIOD
        tri = 2 * abs(2 * phase - 1) - 1
        target = WIGGLE_AMP * tri
        mode = "idle-wiggle"
        pdir = "-"

    err = target - _keeper_pos
    cmd = 0 if abs(err) < POS_DEADBAND else int(max(-MAX_SPEED, min(MAX_SPEED, KP_POS * err)))
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

    _frame_i += 1


def main():
    setup()
    try:
        App.run(user_loop=loop)
    finally:
        if motor is not None:
            try:
                motor.movement_stop()
            except Exception:
                pass
            try:
                motor.disconnect()
            except Exception:
                pass
            print("[main] motor stopped and disconnected")


if __name__ == "__main__":
    main()