"""
Follow-the-line with camera-based obstacle handling.

Line position comes from the LEGO color sensor over BLE and drives a
tabular Q-learner that picks a steering action every tick. Obstacles
come from the video_object_detection Brick (app.yaml, custom Edge
Impulse model with "block"/"minifigure" classes):

    minifigure in view -> stop, resume once it clears
    block in view      -> fixed swerve, then resume line-following

The Q-learner only trains during normal ticks -- ticks spent stopped
or swerving are skipped. The Q-table (and epsilon) is saved to disk
periodically and reloaded on startup so training accumulates across
restarts instead of resetting every run.

drive() and the sensor read are wrapped so a single BLE bridge
timeout just skips that tick instead of crashing the whole run.
"""

import os
import time
import pickle
import threading

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.video_objectdetection import VideoObjectDetection

from lelib import doubleMotor, colorSensor
from qlearner import Calibrator, QLearner, ACTIONS, bin_of

CARD_SERIAL = "1131"
CARD_COLOR = "Red"

DETECTION_CONFIDENCE = 0.6
DEBOUNCE_SEC = 0.05
CLEAR_GRACE_SEC = 0.5
SWERVE_DURATION_SEC = 1.2
SWERVE_SPEED = 70
TICK_SLEEP = 0.05

SPEED_SCALE = 0.2

Q_TABLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "q_table.pkl")
SAVE_EVERY_TICKS = 200
REWARD_WINDOW = 200

ui = WebUI()
detector = VideoObjectDetection(confidence=DETECTION_CONFIDENCE, debounce_sec=DEBOUNCE_SEC)

motor = doubleMotor()
motor.connect(card_serial=CARD_SERIAL, card_color=CARD_COLOR)
sensor = colorSensor()
sensor.connect(card_serial=CARD_SERIAL, card_color=CARD_COLOR)

cal = Calibrator()
learner = QLearner()

last_seen = {"minifigure": 0.0, "block": 0.0}
_lock = threading.Lock()


def _mark(label):
    with _lock:
        last_seen[label] = time.time()


detector.on_detect("minifigure", lambda *a, **kw: _mark("minifigure"))
detector.on_detect("block", lambda *a, **kw: _mark("block"))


def _recently_seen(label, within=CLEAR_GRACE_SEC):
    with _lock:
        return (time.time() - last_seen[label]) < within


def drive(left, right):
    try:
        motor.movement_move_tank(left * SPEED_SCALE, right * SPEED_SCALE)
    except Exception as e:
        print("drive() failed, skipping this tick:", e)


def read_reflection():
    try:
        return sensor.sensor.reflection
    except Exception as e:
        print("sensor read failed, skipping this tick:", e)
        return None


def load_q_table():
    try:
        with open(Q_TABLE_PATH, "rb") as f:
            data = pickle.load(f)
        learner.q = data["q"]
        learner.epsilon = data.get("epsilon", learner.epsilon)
        print("Loaded {} learned state-action values (epsilon={:.3f})".format(
            len(learner.q), learner.epsilon))
    except FileNotFoundError:
        print("No saved Q-table found, starting fresh (with warm-start bias)")


def save_q_table():
    with open(Q_TABLE_PATH, "wb") as f:
        pickle.dump({"q": learner.q, "epsilon": learner.epsilon}, f)


def control_loop():
    mode = "NORMAL"
    swerve_until = 0.0
    tick = 0
    recent_rewards = []

    load_q_table()

    print("Sweeping... move the sensor across the line edge now.")
    time.sleep(1)
    for i in range(100):
        r = read_reflection()
        if r is not None:
            cal.update(r)
            print("raw reflection:", round(r, 1))
        time.sleep(0.05)
    print("calibrated: lo={:.1f} mid={:.1f} hi={:.1f}".format(cal.lo, cal.mid(), cal.hi))

    while True:
        tick += 1

        if _recently_seen("minifigure"):
            mode = "STOP"
        elif mode == "STOP":
            mode = "NORMAL"
            learner.reset_transition()

        if mode == "STOP":
            drive(0, 0)
            ui.send_message("state", {"mode": mode})
            time.sleep(TICK_SLEEP)
            continue

        if _recently_seen("block") and mode != "SWERVE":
            mode = "SWERVE"
            swerve_until = time.time() + SWERVE_DURATION_SEC

        if mode == "SWERVE":
            drive(SWERVE_SPEED, -SWERVE_SPEED)  # fixed direction -- flip if it swerves the wrong way
            if time.time() >= swerve_until:
                mode = "NORMAL"
                learner.reset_transition()
            ui.send_message("state", {"mode": mode})
            time.sleep(TICK_SLEEP)
            continue

        reading = read_reflection()
        if reading is None:
            time.sleep(TICK_SLEEP)
            continue

        cal.update(reading)
        x = cal.normalized(reading)
        state = bin_of(x)

        action = learner.select_action(state)
        left, right = ACTIONS[action]
        drive(left, right)
        reward = learner.observe(x, state)

        if reward is not None:
            recent_rewards.append(reward)
            if len(recent_rewards) > REWARD_WINDOW:
                recent_rewards.pop(0)

        ui.send_message("state", {"mode": mode, "x": round(x, 2), "action": action})

        if tick % SAVE_EVERY_TICKS == 0:
            save_q_table()
            if recent_rewards:
                avg_reward = sum(recent_rewards) / len(recent_rewards)
                print("tick {}  avg reward (last {}): {:.3f}  epsilon={:.3f}".format(
                    tick, len(recent_rewards), avg_reward, learner.epsilon))
                print(learner.policy_summary())

        time.sleep(TICK_SLEEP)


threading.Thread(target=control_loop, daemon=True).start()
App.run()