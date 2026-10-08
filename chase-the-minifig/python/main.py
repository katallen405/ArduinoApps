import threading
import time

from arduino.app_utils import App, Logger
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.object_detection import ObjectDetection
from arduino.app_peripherals.camera import Camera
from arduino.app_utils.image import numpy_to_pil

import lelib as le

logger = Logger("ChaseMinifig")

# ── Hardware & target configuration ──────────────────────────────
# Serial number printed on the double motor's Bluetooth connection card.
# This changes if you re-pair or swap the card - update it here.
MOTOR_SERIAL = "0026"

# Must match the class label the Edge Impulse model (ei-model-1054456-2,
# configured in app.yaml) outputs for the minifigure.
TARGET_LABEL = "minifig"
CONFIDENCE = 0.5

# Lower capture resolution = less to encode/transfer/infer on each frame = higher fps.
# If the camera doesn't support this mode natively, it falls back to the closest one
# and logs a warning - the control loop reads the actual frame size every iteration
# regardless, so no other code needs to change.
CAMERA_RESOLUTION = (320, 320)

# ── Proportional control tuning ──────────────────────────────────
TURN_KP = 5.0  # motor percent applied per unit of normalized horizontal error (-1..1)
MAX_TURN_SPEED = 20.0  # percent, clamps the motor command - kept low since detection only runs at ~1.6 fps
DEADBAND = 0.06  # normalized error under which the target counts as "centered"

# Bounding-box height (as a fraction of frame height) is used as a proxy for distance -
# bigger box = closer. NOTE: this model is a FOMO/"constrained_object_detection" model
# with a 96x96 input, so its boxes come from a coarse activation grid rather than a
# tightly regressed fit - the size signal is blocky/quantized, not perfectly smooth.
# Watch the "distance" tile in the web UI and retune if it feels too jumpy.
FORWARD_KP = 40.0  # motor percent applied per unit of "how much smaller than target size"
FORWARD_MAX_SPEED = 10.0  # percent, clamps forward speed
TARGET_BOX_HEIGHT_FRAC = 0.5  # stop advancing once the box reaches this fraction of frame height
MAX_WHEEL_SPEED = 20.0  # final per-wheel safety clamp after mixing forward + turn

LOST_TARGET_TIMEOUT = 1.0  # seconds without a detection before stopping the motors
LOOP_PERIOD = 0.1  # seconds between camera captures/detections


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


camera = Camera(resolution=CAMERA_RESOLUTION)
camera.start()

object_detection = ObjectDetection(confidence=CONFIDENCE)

motor = le.doubleMotor()
logger.info(f"Connecting to double motor (card_serial={MOTOR_SERIAL})...")
motor.connect(card_serial=MOTOR_SERIAL)
if not motor.connected:
    raise ConnectionError("Could not connect to the LEGO double motor - check MOTOR_SERIAL.")
logger.info("Motor connected.")

ui = WebUI()

# Live camera feed for debugging, shown in the web UI at /camera_preview.
# Comment out this line to disable it once you're done debugging.
ui.expose_camera("/camera_preview", camera)

state_lock = threading.Lock()
state = {
    "action": "starting",
    "label": TARGET_LABEL,
    "confidence": None,
    "error_px": None,
    "error_norm": None,
    "box_height_frac": None,
    "minifig_count": 0,
    "fps": 0.0,
    "frame_ms": None,
}


def publish_state():
    with state_lock:
        snapshot = dict(state)
    ui.send_message("status", snapshot)


ui.on_connect(lambda sid: publish_state())

_last_seen = 0.0
_last_frame_time = None
_was_tracking = False


def loop():
    global _last_seen, _last_frame_time, _was_tracking

    t_capture_start = time.time()
    frame = camera.capture()
    t_captured = time.time()
    if frame is None:
        time.sleep(LOOP_PERIOD)
        return

    pil_image = numpy_to_pil(frame)
    t_converted = time.time()

    result = object_detection.detect(pil_image)
    t_detected = time.time()

    now = t_detected
    frame_ms = (now - _last_frame_time) * 1000 if _last_frame_time else None
    fps = (1000.0 / frame_ms) if frame_ms else 0.0
    _last_frame_time = now

    # Temporary diagnostic: break down where per-frame time actually goes.
    # "detect" includes the PNG encode inside get_image_bytes(), the HTTP POST to
    # the model runner container, and the runner's own resize + inference.
    capture_ms = (t_captured - t_capture_start) * 1000
    convert_ms = (t_converted - t_captured) * 1000
    detect_ms = (t_detected - t_converted) * 1000
    logger.info(f"timing(ms): capture={capture_ms:.0f} convert={convert_ms:.0f} detect={detect_ms:.0f} total={frame_ms}")

    detections = (result or {}).get("detection", [])
    matches = [det for det in detections if det.get("class_name") == TARGET_LABEL]
    minifig_count = len(matches)
    target = max(matches, key=lambda det: float(det["confidence"]), default=None)

    if target is None:
        action = "searching"
        confidence = error_px = error_norm = box_height_frac = None
        if _was_tracking:
            logger.info("Target lost.")
            _was_tracking = False
        if _last_seen and (now - _last_seen) > LOST_TARGET_TIMEOUT:
            motor.movement_move_tank(0, 0)
    else:
        _last_seen = now
        confidence = float(target["confidence"])
        if not _was_tracking:
            logger.info(f"Target acquired (confidence={confidence:.1f}%).")
            _was_tracking = True

        frame_height, frame_width = frame.shape[:2]
        x1, y1, x2, y2 = target["bounding_box_xyxy"]
        cx = (x1 + x2) / 2.0
        frame_center_x = frame_width / 2.0

        error_px = cx - frame_center_x
        error_norm = error_px / frame_center_x if frame_center_x else 0.0

        if abs(error_norm) < DEADBAND:
            turn = 0.0
            turn_action = "centered"
        else:
            turn = clamp(TURN_KP * error_norm, -MAX_TURN_SPEED, MAX_TURN_SPEED)
            turn_action = f"turning {'right' if turn > 0 else 'left'}"

        box_height_frac = (y2 - y1) / frame_height if frame_height else 0.0
        forward = clamp(FORWARD_KP * (TARGET_BOX_HEIGHT_FRAC - box_height_frac), 0.0, FORWARD_MAX_SPEED)
        action = f"{turn_action}, approaching" if forward > 0 else f"{turn_action}, at target distance"

        # Positive error = target right of center -> turn right in place.
        # Mix forward drive with the turn via tank steering. On this hardware, positive
        # motor speed drives the wheels backward, so `forward` (always >= 0) is negated
        # here to actually move the robot toward the target - if it still goes backward,
        # flip this sign again; if it turns the wrong way, swap the sign of `turn` instead.
        left_speed = clamp(-forward + turn, -MAX_WHEEL_SPEED, MAX_WHEEL_SPEED)
        right_speed = clamp(-forward - turn, -MAX_WHEEL_SPEED, MAX_WHEEL_SPEED)
        motor.movement_move_tank(left_speed, right_speed)

    with state_lock:
        state.update(
            action=action,
            confidence=confidence,
            error_px=error_px,
            error_norm=error_norm,
            box_height_frac=box_height_frac,
            minifig_count=minifig_count,
            fps=round(fps, 1),
            frame_ms=round(frame_ms, 1) if frame_ms else None,
        )
    publish_state()

    elapsed = time.time() - t_capture_start
    if elapsed < LOOP_PERIOD:
        time.sleep(LOOP_PERIOD - elapsed)


try:
    App.run(user_loop=loop)
finally:
    # App.run() only auto-stops registered "bricks" - the LEGO motor bridge isn't
    # one, so it never gets released on shutdown unless we do it here. A `finally`
    # around App.run() still fires on stop/SIGTERM: App.run() converts that into
    # sys.exit(), which raises SystemExit and unwinds through this block.
    logger.info("Shutting down - stopping motor and disconnecting.")
    try:
        motor.movement_move_tank(0, 0)
    except Exception:
        logger.exception("Failed to stop motor cleanly.")
    try:
        motor.disconnect()
    except Exception:
        logger.exception("Failed to disconnect motor cleanly.")
