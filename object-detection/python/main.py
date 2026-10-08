"""Object-detection person-following LEGO robot, with distance estimation
and a forward-sweep search behavior.

Runs on the Arduino UNO Q's Linux side. The `video_object_detection` Brick
(configured in app.yaml) runs a custom Edge Impulse object-detection model.
The robot follows the "minifig" class only - any other detected classes
(e.g. "block") are ignored entirely.

Behavior, checked every frame:
  1. If a "minifig" is seen -> steer toward it, estimating real distance in
     cm from its pixel height (needs one-time calibration), and stop once
     close enough instead of continuously re-adjusting. If more than one
     minifig is visible, keeps tracking whichever one it already locked
     onto (by proximity to its last-seen position) instead of jumping to a
     different, possibly larger one.
  2. If it disappears right after being close (about to arrive) -> stop,
     since it most likely just left the camera's field of view from being
     too close, rather than wandered off to one side.
  3. Otherwise, for a while -> drive forward while sweeping the steering
     left/right, scanning side to side while advancing instead of
     spinning in place. The sweep's first swing leans toward whichever
     side the minifig was last seen on, then continues sweeping normally.
  4. If still not found after the search window -> stop.

Detections still get streamed to the Web UI as raw coordinates
(x, y, width, height, centroid, estimated distance) alongside the
bounding-box video overlay the brick already draws for you.
"""

import atexit
import json
import math
import os
import signal
import sys
import threading
import time
from datetime import datetime, UTC

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.video_objectdetection import VideoObjectDetection

from lelib import doubleMotor

# ── Configuration ────────────────────────────────────────────────────────

TARGET_LABEL = "minifig"     # what the robot follows; every other detected
                              # class is ignored entirely

DETECTION_CONFIDENCE = 0.8  # raised from 0.6 for more reliable detections
DEBOUNCE_SEC = 0.0  # 0 = fire on every processed frame (needed for continuous control)

# Frame size the reported bounding-box coordinates (x, y, w, h) are relative
# to. This is NOT the model's internal processing size (Studio's "Create
# impulse" -> Image input block shows 96x96 for this project's model) - the
# video_object_detection brick rescales detections back up to the camera's
# native capture resolution before handing them to on_detections(), so this
# constant has to match THAT, not Studio's number.
#
# Re-derived empirically (2nd time - see DECISIONS.md #2 for the first):
# debug output never showed x beyond 480 or y beyond 400, and 640x480 is
# both a standard USB webcam resolution and divides evenly into the
# observed 40px grid cells in both dimensions (16x12 cells) - matching the
# FOMO quantization pattern. It also matches the video panel's `aspect-ratio:
# 4/3` in style.css, which never matched the old 320x320 (square) assumption.
# If this model or camera is ever swapped, re-verify by checking max x/y in
# fresh debug output rather than assuming this still applies.
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Following (minifig) tuning
STEER_GAIN = 10.0          # lowered further from 18 - slower turning
BASE_TURN_DEADZONE = 0.05
TARGET_AREA_RATIO = 0.0133  # fallback distance proxy used only if not calibrated -
                            # rescaled by (320*320)/(640*480) = 1/3 from the old
                            # 0.04, which was tuned against the wrong (320x320)
                            # frame area assumption
DISTANCE_GAIN = 25.0       # lowered further from 45 - slower approach
MAX_SPEED = 12             # lowered further from 20 - overall speed cap, percent (-100..100)

# Real-world distance estimation
KNOWN_MINIFIG_HEIGHT_CM = 4.7   # standard LEGO minifig height - adjust if yours differs
TARGET_DISTANCE_CM = 22.9       # desired following distance once calibrated - ~9 inches
DISTANCE_GAIN_CM = 0.35         # lowered further from 0.6 - speed per cm of distance error
CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")

# Approaching the minifig: stop once close enough instead of continuously
# nudging back and forth to hold an exact distance. ARRIVE_HYSTERESIS adds a
# buffer so it doesn't flicker between "arrived" and "approaching" right at
# the boundary - it only resumes approaching once the minifig has moved
# clearly farther away again.
ARRIVE_HYSTERESIS_CM = 5.0
ARRIVE_HYSTERESIS_AREA = 0.0067  # rescaled by 1/3 alongside TARGET_AREA_RATIO

# Losing / searching for the target
LOST_TARGET_AFTER_MISSES = 6     # consecutive empty frames before "searching" starts
SEARCH_TIMEOUT_MISSES = 40        # additional misses allowed while searching before giving up
SEARCH_FORWARD_SPEED = 6            # lowered further from 10 - base forward speed while searching
SEARCH_SWEEP_AMPLITUDE = 4          # lowered further from 7 - how hard to swing left/right while advancing
SEARCH_SWEEP_PERIOD_MISSES = 20    # frames per full left-right-left sweep cycle

# LEGO Double Motor hub identity (unchanged from original gesture app)
MOTOR_CARD_SERIAL = "0026"
MOTOR_CARD_COLOR = "Green"

# If both wheels are commanded the same "forward" speed but the robot spins
# in place instead of driving straight, the two motors are physically
# mounted facing opposite directions (common on two-wheel chassis) - the
# same signed speed spins one wheel forward and the other backward. Flip
# EXACTLY ONE of these to True to correct it - try MOTOR_INVERT_RIGHT first;
# if that makes it worse instead of better, set it back to False and set
# MOTOR_INVERT_LEFT to True instead.
MOTOR_INVERT_LEFT = True
MOTOR_INVERT_RIGHT = True

# BLE pairing to the Double Motor hub can be flaky right after the container
# starts. Retry with backoff instead of crashing the whole app; keep retrying
# in the background if it still fails so it reconnects on its own once the
# hardware issue (hub asleep / already paired elsewhere / out of range) is
# fixed, without needing a redeploy.
MOTOR_CONNECT_STARTUP_ATTEMPTS = 5
MOTOR_CONNECT_STARTUP_DELAY_SEC = 3
MOTOR_RECONNECT_INTERVAL_SEC = 5

# ── Setup ────────────────────────────────────────────────────────────────

ui = WebUI()

detector = VideoObjectDetection(confidence=DETECTION_CONFIDENCE, debounce_sec=DEBOUNCE_SEC)

motor = doubleMotor()

_motor_connected = False
_motor_lock = threading.Lock()


def _try_connect_motor():
    global _motor_connected
    try:
        motor.connect(card_serial=MOTOR_CARD_SERIAL, card_color=MOTOR_CARD_COLOR)
        with _motor_lock:
            _motor_connected = True
        print("Motor connected.")
        ui.send_message("motor_status", {"connected": True})
        return True
    except Exception as e:
        with _motor_lock:
            _motor_connected = False
        print(f"Motor connect failed: {e}")
        return False


def _motor_watchdog():
    """Keeps retrying in the background whenever the motor isn't connected,
    so the app recovers on its own once the hardware issue is fixed."""
    while True:
        with _motor_lock:
            connected = _motor_connected
        if not connected:
            _try_connect_motor()
        time.sleep(MOTOR_RECONNECT_INTERVAL_SEC)


def is_motor_connected():
    with _motor_lock:
        return _motor_connected


def safe_move_tank(left_speed, right_speed):
    if not is_motor_connected():
        return
    # Everything else in this file thinks in "positive = forward" terms for
    # both wheels; only here, right at the hardware boundary, do we correct
    # for a physically-mirrored motor mount.
    hw_left = -left_speed if MOTOR_INVERT_LEFT else left_speed
    hw_right = -right_speed if MOTOR_INVERT_RIGHT else right_speed
    try:
        motor.movement_move_tank(hw_left, hw_right)
    except Exception as e:
        print(f"MOTOR ERROR (tank drive): {e}")
        with _motor_lock:
            global _motor_connected
            _motor_connected = False
        ui.send_message("motor_status", {"connected": False})


# Try a few times at startup (BLE can take a moment right after the
# container comes up), then keep trying in the background regardless of
# whether the first attempt succeeded - camera/detection/Web UI all still
# work even if the motor never connects.
for _attempt in range(MOTOR_CONNECT_STARTUP_ATTEMPTS):
    if _try_connect_motor():
        break
    time.sleep(MOTOR_CONNECT_STARTUP_DELAY_SEC)

if not is_motor_connected():
    print("Motor not connected after startup attempts - app will keep running "
          "(detection + Web UI still work) and retry in the background. "
          "Check: hub powered on and awake, not paired elsewhere, in range, "
          "and MOTOR_CARD_SERIAL/MOTOR_CARD_COLOR match your hub's ID card.")

threading.Thread(target=_motor_watchdog, daemon=True).start()


# Explicitly disconnect the motor when the app stops, so the LEGO hub's BLE
# session is released cleanly instead of being left dangling. A stale
# connection from an ungracefully-killed previous run is a common cause of
# the *next* run's motor.connect() hanging/timing out, since the hub still
# thinks it's connected to the old session.
def _cleanup(signum=None, frame=None):
    print("Shutting down - disconnecting motor if connected...")
    try:
        if is_motor_connected():
            motor.disconnect()
            print("Motor disconnected cleanly.")
    except Exception as e:
        print(f"Error while disconnecting motor: {e}")
    if signum is not None:
        sys.exit(0)


signal.signal(signal.SIGTERM, _cleanup)
signal.signal(signal.SIGINT, _cleanup)
atexit.register(_cleanup)

_miss_count = 0
_hit_count = 0
_lock = threading.Lock()

# A minifig detection must repeat this many consecutive frames before it's
# trusted (steered toward, drawn as the overlay box, reported as "following")
# - filters out single-frame false positives (e.g. the model firing on a
# blank/overexposed frame) instead of reacting to every spurious blip.
CONFIRM_HITS_REQUIRED = 2

# Rolling window of recent inter-frame gaps, for a smoothed FPS estimate sent
# to the Web UI. Measured directly from on_detections() call timing rather
# than counting UI messages, since some frames return early without sending
# telemetry (e.g. a brief single-frame miss) and would otherwise undercount.
_last_frame_time = None
_frame_intervals = []
FPS_WINDOW = 20

# Remembers the last place the minifig was actually seen, so we know which
# way to turn while searching for it.
_last_seen = {"cx_norm": 0.0, "height_px": None, "area_ratio": None, "time": None}

# The centroid (in model-space pixels) of the minifig we're currently
# tracking. Keeps us following the SAME minifig across frames even if a
# second minifig (or a stray false-positive) appears elsewhere in view,
# instead of jumping to whichever detected instance has the largest box.
# Cleared once the target is fully lost (search window times out), so the
# next detection starts a fresh acquisition.
_locked_centroid = None

# Whether the robot has already reached its target following distance from
# the minifig (used to stop-and-hold instead of continuously re-adjusting).
_arrived = False

_focal_length_px = None  # loaded from disk if a calibration has been done


def _load_calibration():
    global _focal_length_px
    try:
        with open(CALIBRATION_FILE) as f:
            data = json.load(f)
            _focal_length_px = data.get("focal_length_px")
            print(f"Loaded calibration: focal_length_px={_focal_length_px}")
    except (FileNotFoundError, json.JSONDecodeError):
        print("No calibration file found yet - distance will be uncalibrated until you calibrate.")


def _save_calibration():
    with open(CALIBRATION_FILE, "w") as f:
        json.dump({"focal_length_px": _focal_length_px}, f)


_load_calibration()


def clip(value, lo, hi):
    return max(lo, min(hi, value))


def pick_best_instance(instances):
    """Pick the instance to track. If we're already locked onto a minifig,
    stick with whichever instance is closest to where it was last seen, so a
    second minifig (or a spurious detection) appearing nearby doesn't steal
    the lock just because its box happens to be bigger. Otherwise (no target
    locked yet - e.g. right after startup or after fully losing the target),
    acquire the largest/most confident instance."""
    if _locked_centroid is not None:
        lx, ly = _locked_centroid

        def dist_to_lock(inst):
            _, _, _, _, cx, cy, _ = box_metrics(inst)
            return (cx - lx) ** 2 + (cy - ly) ** 2

        return min(instances, key=dist_to_lock)

    def area_and_conf(inst):
        x_min, y_min, x_max, y_max = inst["bounding_box_xyxy"]
        w, h = x_max - x_min, y_max - y_min
        return (w * h, inst["confidence"])

    return max(instances, key=area_and_conf)


def box_metrics(inst):
    x_min, y_min, x_max, y_max = inst["bounding_box_xyxy"]
    w, h = x_max - x_min, y_max - y_min
    cx, cy = x_min + w // 2, y_min + h // 2
    area_ratio = (w * h) / (FRAME_WIDTH * FRAME_HEIGHT)
    return x_min, y_min, w, h, cx, cy, area_ratio


def estimate_distance_cm(pixel_height):
    if not _focal_length_px or pixel_height <= 0:
        return None
    return (KNOWN_MINIFIG_HEIGHT_CM * _focal_length_px) / pixel_height


def stop_motor():
    safe_move_tank(0, 0)


def send_telemetry(mode, **fields):
    ui.send_message("telemetry", {
        "mode": mode,  # "following" | "searching" | "lost"
        "motor_connected": is_motor_connected(),
        "timestamp": datetime.now(UTC).isoformat(),
        **fields,
    })


def on_detections(detections: dict):
    global _miss_count, _hit_count, _arrived, _locked_centroid, _last_frame_time

    now = time.monotonic()
    if _last_frame_time is not None:
        interval = now - _last_frame_time
        if interval > 0:
            _frame_intervals.append(interval)
            if len(_frame_intervals) > FPS_WINDOW:
                _frame_intervals.pop(0)
    _last_frame_time = now
    if _frame_intervals:
        avg_interval = sum(_frame_intervals) / len(_frame_intervals)
        ui.send_message("fps", {"fps": round(1.0 / avg_interval, 1) if avg_interval > 0 else 0.0})

    # DEBUG: prints exactly what the model returned this frame - remove or
    # comment out once things are working as expected. Watch this with:
    #   docker logs -f object-detection-main-1
    # x/y are included specifically to empirically re-derive FRAME_WIDTH/
    # FRAME_HEIGHT if they're ever wrong - move the target to each edge of
    # the camera's view and note the largest x and y values seen.
    if detections:
        for lbl, instances in detections.items():
            for inst in instances:
                x, y, w, h, _, _, ar = box_metrics(inst)
                print(f"DEBUG saw '{lbl}' conf={inst['confidence']:.2f} "
                      f"x={x} y={y} w={w} h={h} area_ratio={ar:.4f}")
    else:
        print("DEBUG saw nothing this frame")

    target_instances = detections.get(TARGET_LABEL, [])

    # Follow the minifig - approach, then stop once close enough
    if target_instances:
        with _lock:
            _miss_count = 0
            _hit_count += 1
            hits = _hit_count

        if hits < CONFIRM_HITS_REQUIRED:
            return  # not confirmed yet - could be a one-off false positive

        best = pick_best_instance(target_instances)
        x, y, w, h, cx, cy, area_ratio = box_metrics(best)
        cx_norm = ((cx / FRAME_WIDTH) - 0.5) * 2.0  # -1 (left) .. +1 (right)

        _locked_centroid = (cx, cy)

        _last_seen["cx_norm"] = cx_norm
        _last_seen["height_px"] = h
        _last_seen["area_ratio"] = area_ratio
        _last_seen["time"] = datetime.now(UTC)

        distance_cm = estimate_distance_cm(h)

        if distance_cm is not None:
            if not _arrived and distance_cm <= TARGET_DISTANCE_CM:
                _arrived = True
            elif _arrived and distance_cm > TARGET_DISTANCE_CM + ARRIVE_HYSTERESIS_CM:
                _arrived = False
        else:
            # Not calibrated yet: use box-size proxy instead
            if not _arrived and area_ratio >= TARGET_AREA_RATIO:
                _arrived = True
            elif _arrived and area_ratio < TARGET_AREA_RATIO - ARRIVE_HYSTERESIS_AREA:
                _arrived = False

        if _arrived:
            left_speed, right_speed = 0, 0
        else:
            turn_error = cx_norm if abs(cx_norm) > BASE_TURN_DEADZONE else 0.0
            turn = STEER_GAIN * turn_error

            if distance_cm is not None:
                distance_error = distance_cm - TARGET_DISTANCE_CM  # positive => too far -> forward
                forward = clip(DISTANCE_GAIN_CM * distance_error, 0, MAX_SPEED)
            else:
                distance_error = TARGET_AREA_RATIO - area_ratio
                forward = clip(DISTANCE_GAIN * distance_error, 0, MAX_SPEED)

            left_speed = clip(forward + turn, -MAX_SPEED, MAX_SPEED)
            right_speed = clip(forward - turn, -MAX_SPEED, MAX_SPEED)

        safe_move_tank(left_speed, right_speed)

        send_telemetry(
            "following", label=TARGET_LABEL, confidence=best["confidence"],
            x=x, y=y, width=w, height=h, cx=cx, cy=cy, cx_norm=round(cx_norm, 3),
            area_ratio=round(area_ratio, 4),
            distance_cm=round(distance_cm, 1) if distance_cm is not None else None,
            arrived=_arrived,
            left_speed=round(left_speed, 1), right_speed=round(right_speed, 1),
        )
        return

    # Nothing relevant seen this frame
    with _lock:
        _miss_count += 1
        misses = _miss_count
        _hit_count = 0

    if misses < LOST_TARGET_AFTER_MISSES:
        return  # brief gap, e.g. a dropped frame - don't react yet

    # If the minifig was already close (near TARGET_DISTANCE_CM, or a large
    # area_ratio if uncalibrated) right before it disappeared, it most likely
    # just went out of the camera's field of view because the robot got too
    # close to still see it - not because it wandered off to one side.
    # Driving forward to "search" in that case would push the robot further
    # into/past where the minifig actually is. Stop instead.
    last_distance_cm = estimate_distance_cm(_last_seen["height_px"])
    if last_distance_cm is not None:
        was_close = last_distance_cm <= TARGET_DISTANCE_CM + ARRIVE_HYSTERESIS_CM
    else:
        was_close = (
            _last_seen["area_ratio"] is not None
            and _last_seen["area_ratio"] >= TARGET_AREA_RATIO - ARRIVE_HYSTERESIS_AREA
        )

    if was_close:
        stop_motor()
        _locked_centroid = None
        send_telemetry("lost", reason="was close when target left view - stopped instead of searching")
        return

    if misses < LOST_TARGET_AFTER_MISSES + SEARCH_TIMEOUT_MISSES:
        # Searching: drive forward while sweeping the steering left/right,
        # like scanning side to side while advancing, instead of spinning
        # in place. The sweep is phase-shifted so the first swing leans
        # toward whichever side the minifig was last seen on (remembered in
        # _last_seen["cx_norm"]), instead of a direction-blind sweep that
        # might initially turn away from where it actually went.
        search_progress = misses - LOST_TARGET_AFTER_MISSES
        last_cx = _last_seen["cx_norm"]
        phase_offset = math.copysign(math.pi / 2, last_cx) if last_cx else 0.0
        sweep = SEARCH_SWEEP_AMPLITUDE * math.sin(
            2 * math.pi * search_progress / SEARCH_SWEEP_PERIOD_MISSES + phase_offset
        )
        left_speed = clip(SEARCH_FORWARD_SPEED - sweep, -MAX_SPEED, MAX_SPEED)
        right_speed = clip(SEARCH_FORWARD_SPEED + sweep, -MAX_SPEED, MAX_SPEED)

        safe_move_tank(left_speed, right_speed)

        send_telemetry(
            "searching",
            last_cx_norm=round(_last_seen["cx_norm"], 3),
            last_distance_cm=round(estimate_distance_cm(_last_seen["height_px"]), 1)
                if _last_seen["height_px"] else None,
            left_speed=round(left_speed, 1), right_speed=round(right_speed, 1),
        )
        return

    # Search window expired - give up
    stop_motor()
    _locked_centroid = None
    send_telemetry("lost")


# ── Live-tunable parameters + calibration from the Web UI ────────────────

def _set_confidence(sid, value):
    detector.override_threshold(float(value))


def _set_steer_gain(sid, value):
    global STEER_GAIN
    STEER_GAIN = float(value)


def _set_target_area(sid, value):
    global TARGET_AREA_RATIO
    TARGET_AREA_RATIO = float(value)


def _set_target_distance_cm(sid, value):
    global TARGET_DISTANCE_CM
    TARGET_DISTANCE_CM = float(value)


def _calibrate_distance(sid, known_distance_cm):
    """Call this with the minifig held at `known_distance_cm` in front of the
    camera right now. Uses the most recently seen pixel height to solve for
    focal length, then saves it so distance estimation works from now on."""
    global _focal_length_px
    height_px = _last_seen["height_px"]
    if not height_px:
        ui.send_message("calibration_result", {"ok": False, "reason": "No minifig currently visible."})
        return
    _focal_length_px = (float(known_distance_cm) * height_px) / KNOWN_MINIFIG_HEIGHT_CM
    _save_calibration()
    ui.send_message("calibration_result", {
        "ok": True, "focal_length_px": round(_focal_length_px, 1),
        "at_distance_cm": known_distance_cm, "height_px": height_px,
    })


ui.on_message("override_th", _set_confidence)
ui.on_message("set_steer_gain", _set_steer_gain)
ui.on_message("set_target_area", _set_target_area)
ui.on_message("set_target_distance_cm", _set_target_distance_cm)
ui.on_message("calibrate_distance", _calibrate_distance)

detector.on_detect_all(on_detections)

App.run()