import threading
import time

import cv2

from arduino.app_bricks.video_objectdetection import VideoObjectDetection
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App, Logger

import lelib as le


# Set to False to restore the original design: a double-motor drive base plus 3
# separate stamping arms (one per object), connecting all 4 motors. True connects
# only ONE motor and rotates it to a different angle per detected object, so you
# can test camera/detection end-to-end without depending on all 4 motors' Bluetooth
# connections at once. Search "ORIGINAL DESIGN" below to find what's preserved.
SINGLE_MOTOR_TEST_MODE = True

# Change these to your Bluetooth connection-card details.
DRIVE_CARD = {
    "color": "magenta",
    "serial": "2288",
}
LEFT_ARM_CARD = {
    "color": "orange",
    "serial": "7590",
}
MIDDLE_ARM_CARD = {
    "color": "purple",
    "serial": "0049",
}
RIGHT_ARM_CARD = {
    "color": "yellow",
    "serial": "1126",
}

# TEST MODE: the single test motor reuses the middle arm's card, since that's the
# one that's been connecting reliably.
TEST_MOTOR_CARD = MIDDLE_ARM_CARD

# These must match your Edge Impulse labels EXACTLY - VideoObjectDetection.on_detect()
# matches label strings verbatim, with no normalization.
RAT_LABEL = "rat"
CAR_LABEL = "car"
MINIFIGURE_LABEL = "minifigure"

CONFIDENCE = 0.60
STAMP_COOLDOWN_SECONDS = 2.0  # passed to VideoObjectDetection as its per-label debounce
ARM_DEGREES = 180
ARM_SPEED = 35
CAMERA_RESOLUTION = (320, 320)

# ORIGINAL DESIGN: if one arm moves up instead of down, change its value from 1 to -1.
ARM_DOWN_DIRECTION = {
    "left": 1,
    "middle": 1,
    "right": 1,
}

# TEST MODE: absolute position (in degrees) the single test motor moves to for each
# detected object. Change these to whatever angles you want to test.
TEST_MOTOR_POSITIONS = {
    RAT_LABEL: 0,
    CAR_LABEL: 120,
    MINIFIGURE_LABEL: 240,
}

# Edge Impulse reports bounding_box_xyxy in the MODEL's input resolution, not the
# camera's actual capture resolution (which V4LCamera may adjust, e.g. to 352x288
# even though CAMERA_RESOLUTION requests 320x320) - these coordinates get scaled to
# the real frame size before drawing. Check the overlay visually and adjust this if
# boxes look consistently off.
MODEL_INPUT_SIZE = 320

# How long a detection's box/label stays drawn on the live feed after it fires,
# so it doesn't flicker on for one frame and vanish before you can see it.
DETECTION_OVERLAY_TTL_SECONDS = 1.5

logger = Logger("ObjectStamper")

# TEMPORARY diagnostic: legoeducation.py only defines MOTOR_MOVE_DIRECTION_CLOCKWISE
# (and the other MOTOR_*/MOVEMENT_* constants stamp() depends on) if its startup call
# to the LEGO bridge succeeds - that failure is silently swallowed there, so this
# confirms whether the constants actually exist before we ever try to use them.
logger.info(
    "le.MOTOR_MOVE_DIRECTION_CLOCKWISE="
    f"{getattr(le, 'MOTOR_MOVE_DIRECTION_CLOCKWISE', 'MISSING')}, "
    "le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE="
    f"{getattr(le, 'MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE', 'MISSING')}"
)

# Sharing this one Camera instance with VideoObjectDetection (below) is required:
# the brick starts/stops whatever camera it's given, and creates its own default
# Camera() if none is passed - passing ours here is what stops it from opening the
# physical USB camera a second time (that double-open was crashing the app).
camera = Camera(resolution=CAMERA_RESOLUTION)
detector = VideoObjectDetection(camera=camera, confidence=CONFIDENCE, debounce_sec=STAMP_COOLDOWN_SECONDS)
ui = WebUI()


class AnnotatedCamera:
    """Wraps the real camera and draws the most recent detection's bounding box and
    label onto each frame before WebUI streams it, so the live feed shows roughly
    where the model saw something. WebUI.expose_camera() only needs .is_started,
    .start(), and .capture() - it doesn't check the object's actual type - so this
    doesn't need to be a real Camera subclass."""

    is_started = True  # the real camera is already started via VideoObjectDetection

    def __init__(self, base_camera):
        self._camera = base_camera
        self._lock = threading.Lock()
        self._detections = {}
        self._detections_time = 0.0

    def start(self):
        pass  # no-op: the real camera's lifecycle is owned by VideoObjectDetection

    def set_detections(self, detections):
        with self._lock:
            self._detections = detections
            self._detections_time = time.time()

    def capture(self):
        frame = self._camera.capture()
        if frame is None:
            return None

        with self._lock:
            detections = self._detections
            age = time.time() - self._detections_time

        if age > DETECTION_OVERLAY_TTL_SECONDS:
            return frame

        frame_height, frame_width = frame.shape[:2]
        scale_x = frame_width / MODEL_INPUT_SIZE
        scale_y = frame_height / MODEL_INPUT_SIZE

        for label, boxes in detections.items():
            for box in boxes:
                x1, y1, x2, y2 = box["bounding_box_xyxy"]
                x1, y1 = int(x1 * scale_x), int(y1 * scale_y)
                x2, y2 = int(x2 * scale_x), int(y2 * scale_y)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    f"{label} {box['confidence']:.2f}",
                    (x1, max(y1 - 6, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

        return frame


annotated_camera = AnnotatedCamera(camera)

# ORIGINAL DESIGN: one drive motor plus 3 stamping arms.
drive = le.doubleMotor()
left_arm = le.singleMotor()
middle_arm = le.singleMotor()
right_arm = le.singleMotor()

arms = {
    "left": left_arm,
    "middle": middle_arm,
    "right": right_arm,
}

# TEST MODE: single motor, reusing the middle arm's motor object.
test_motor = middle_arm

# VideoObjectDetection dispatches on_detect callbacks from its own thread pool, so
# two different labels could otherwise try to move the same motor at the same time.
# These locks serialize actual motor movement.
arm_locks = {name: threading.Lock() for name in arms}
test_motor_lock = threading.Lock()

state_lock = threading.Lock()
DEFAULT_STATUS = "watching for rat, car, or minifigure"
state = {
    "status": DEFAULT_STATUS,
    "last_detection": "none",
    "last_stamp": "none",
}


def publish_state():
    with state_lock:
        ui.send_message("status", dict(state))


def stamp(arm_name, detected_label):
    """ORIGINAL DESIGN: move one arm down 180 degrees, then back up. Unused while
    SINGLE_MOTOR_TEST_MODE is True."""
    with arm_locks[arm_name]:
        arm = arms[arm_name]
        direction = ARM_DOWN_DIRECTION[arm_name]

        if direction > 0:
            down_direction = le.MOTOR_MOVE_DIRECTION_CLOCKWISE
            up_direction = le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE
        else:
            down_direction = le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE
            up_direction = le.MOTOR_MOVE_DIRECTION_CLOCKWISE

        logger.info(f"Stamping {detected_label} with {arm_name} arm.")

        with state_lock:
            state.update(
                status=f"stamping {detected_label}",
                last_detection=detected_label,
                last_stamp=detected_label,
            )
        publish_state()

        arm.motor_run_for_degrees(
            ARM_DEGREES,
            direction=down_direction,
            speed=ARM_SPEED,
        )

        arm.motor_run_for_degrees(
            ARM_DEGREES,
            direction=up_direction,
            speed=ARM_SPEED,
        )

        arm.stop()

        with state_lock:
            state.update(status=DEFAULT_STATUS)
        publish_state()


def move_test_motor(detected_label):
    """TEST MODE: rotate the single test motor to a different absolute position for
    each detected object."""
    position = TEST_MOTOR_POSITIONS.get(detected_label)
    if position is None:
        return

    with test_motor_lock:
        logger.info(f"Moving test motor to {position} degrees for {detected_label}.")

        with state_lock:
            state.update(
                status=f"moving to {position} degrees for {detected_label}",
                last_detection=detected_label,
                last_stamp=detected_label,
            )
        publish_state()

        test_motor.motor_go_to_position(position, speed=ARM_SPEED)

        with state_lock:
            state.update(status=DEFAULT_STATUS)
        publish_state()


def make_handler(callback, *args):
    def handler():
        # VideoObjectDetection dispatches this on its own thread pool - an unhandled
        # exception here would otherwise vanish silently with no log at all, so this
        # try/except is what lets us see failures instead of just missing movements.
        try:
            callback(*args)
        except Exception:
            logger.exception(f"Handler failed for args={args!r}.")
    return handler


if SINGLE_MOTOR_TEST_MODE:
    for label in (RAT_LABEL, CAR_LABEL, MINIFIGURE_LABEL):
        detector.on_detect(label, make_handler(move_test_motor, label))
else:
    # ORIGINAL DESIGN: each object triggers its own arm.
    detector.on_detect(RAT_LABEL, make_handler(stamp, "right", RAT_LABEL))
    detector.on_detect(CAR_LABEL, make_handler(stamp, "left", CAR_LABEL))
    detector.on_detect(MINIFIGURE_LABEL, make_handler(stamp, "middle", MINIFIGURE_LABEL))


def on_any_detection(detections):
    # TEMPORARY diagnostic: on_detect() only fires for labels we've registered above
    # the confidence threshold, so it can't tell us what the model is ACTUALLY seeing
    # when nothing moves. This fires for every raw detection message so we can check
    # the real label spelling and confidence values in the logs. Remove once detection
    # is confirmed working.
    logger.info(f"Raw detections this frame: {detections}")
    annotated_camera.set_detections(detections)


detector.on_detect_all(on_any_detection)


def connect_motor(motor, card, name):
    logger.info(
        f"Connecting {name} "
        f"(color={card['color']}, serial={card['serial']})"
    )
    try:
        motor.connect(card_color=card["color"], card_serial=card["serial"])
    except Exception:
        # TEMPORARY: don't let one offline motor block camera/detection/WebUI from
        # starting - remove this try/except once all motors connect reliably again.
        logger.exception(f"Could not connect {name} - continuing without it.")
    return motor


def idle_loop():
    # VideoObjectDetection runs its own background threads and invokes on_detect
    # handlers directly, so there's no per-frame work left for the user loop to do.
    time.sleep(1)


try:
    ui.expose_camera("/camera_preview", annotated_camera)
    ui.on_connect(lambda _sid: publish_state())

    if SINGLE_MOTOR_TEST_MODE:
        connect_motor(test_motor, TEST_MOTOR_CARD, "test motor")
    else:
        # ORIGINAL DESIGN: connect the drive base and all 3 stamping arms.
        connect_motor(drive, DRIVE_CARD, "wheel motor")
        connect_motor(left_arm, LEFT_ARM_CARD, "left stamping motor")
        connect_motor(middle_arm, MIDDLE_ARM_CARD, "middle stamping motor")
        connect_motor(right_arm, RIGHT_ARM_CARD, "right stamping motor")

        # Keeps the wheels still while the stamping arms operate.
        drive.stop()

    App.run(user_loop=idle_loop)

finally:
    motors_to_release = (
        (test_motor,) if SINGLE_MOTOR_TEST_MODE else (drive, left_arm, middle_arm, right_arm)
    )
    for motor in motors_to_release:
        try:
            motor.stop()
            motor.disconnect()
        except Exception:
            logger.exception("Could not cleanly stop a motor.")