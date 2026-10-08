"""
LEGO Education brick -- runs inside the `main` app container.

Thin RPC proxy: no Bluetooth here. Every call is forwarded over Arduino's
msgpack-RPC router to agent.py in the `lego-ble` sidecar, which is the only
place legoeducation and bleak actually run.
"""

import json
import uuid

from arduino.app_utils import Bridge

__all__ = ["SingleMotor", "DoubleMotor", "ColorSensor", "Controller", "LegoError"]

DEFAULT_TIMEOUT = 30    # movement and connect/scan can legitimately take a while
CONTROL_TIMEOUT = 10    # bookkeeping calls that never wait on the radio

# Hoisted so there's exactly one place to correct a wrong constant name.
_CW = "MOTOR_MOVE_DIRECTION_CLOCKWISE"
_CCW = "MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE"
_FORWARD = "MOVEMENT_MOVE_DIRECTION_FORWARD"
_BACKWARD = "MOVEMENT_MOVE_DIRECTION_BACKWARD"
_TURN_LEFT = "MOVEMENT_TURN_DIRECTION_LEFT"
_TURN_RIGHT = "MOVEMENT_TURN_DIRECTION_RIGHT"


class LegoError(RuntimeError):
    pass


def _rpc(name, *args, timeout=DEFAULT_TIMEOUT):
    try:
        return Bridge.call(name, *args, timeout=timeout)
    except Exception as exc:
        raise LegoError(f"{name} failed: {exc}") from None


def _decode(raw):
    """agent.py returns results as JSON strings; scalars pass straight through."""
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _spin(clockwise):
    return _CW if clockwise else _CCW


def _color_const(name):
    name = name.upper()
    return name if name.startswith("LEGO_COLOR_") else f"LEGO_COLOR_{name}"


def _check_rate(delay_ms):
    if delay_ms != 0 and not (15 <= delay_ms <= 1000):
        raise ValueError(f"delay_ms must be 0 (off) or 15..1000, got {delay_ms}")
    return int(delay_ms)


class _Device:
    """Shared behavior for SingleMotor, DoubleMotor, ColorSensor, Controller."""

    _le_class = None

    def __init__(self, card_color=None, card_serial=None):
        self._kwargs = {}
        if card_color:
            self._kwargs["card_color"] = card_color
        if card_serial:
            self._kwargs["card_serial"] = card_serial

    def _send(self, method, *args, timeout=DEFAULT_TIMEOUT):
        return _decode(_rpc(method, self._le_class, self._kwargs, *args, timeout=timeout))

    # --- connection lifecycle ---

    def connect(self):
        """Force a connection now. Optional -- call()/read() connect on first use."""
        return self._send("lego.connect")

    def disconnect(self):
        return self._send("lego.disconnect")

    @property
    def connected(self):
        return bool(self.read("connected"))

    # --- generic access to anything not wrapped by name below ---

    def call(self, method, *args, wait=True, on_done=None, timeout=DEFAULT_TIMEOUT, **kwargs):
        """wait=True blocks until the device call returns. wait=False dispatches
        and returns at once; pass on_done(result) to be told when it finishes,
        where result is {'ok': True, 'result': ...} or {'ok': False, 'error': ...}."""
        if wait:
            return self._send("lego.call", method, list(args), kwargs, timeout=timeout)
        channel = f"lego.done.{uuid.uuid4().hex}"
        if on_done is not None:
            Bridge.provide(channel, on_done)
        self._send("lego.call_async", method, list(args), kwargs, channel, timeout=CONTROL_TIMEOUT)
        return channel

    def read(self, path, index=None, timeout=DEFAULT_TIMEOUT):
        return self._send("lego.get", path, index, timeout=timeout)

    def describe(self):
        """Public methods/attributes of the underlying legoeducation object."""
        return self._send("lego.describe", timeout=CONTROL_TIMEOUT)

    # --- real-time push updates ---

    def set_notification_rate(self, delay_ms):
        """Hardware reporting interval. 0 turns notifications off; otherwise
        15..1000 ms (~66 Hz to 1 Hz). Applies at the hub, so a slower rate
        genuinely reduces BLE traffic rather than just discarding data."""
        return self._send("lego.notification_rate", _check_rate(delay_ms),
                          timeout=CONTROL_TIMEOUT)

    def on_update(self, handler, rate_ms=None, min_interval=0):
        """Call handler(data) on every push from this device; data['_type']
        identifies the notification kind.

        rate_ms      -- hardware reporting interval (0, or 15..1000 ms).
        min_interval -- seconds; additionally caps handler calls per type,
                        filtered in the sidecar so dropped events cost nothing.

        Returns a function that unsubscribes.
        """
        channel = f"lego.notify.{uuid.uuid4().hex}"
        Bridge.provide(channel, handler)
        self._send("lego.subscribe", channel, float(min_interval),
                   None if rate_ms is None else _check_rate(rate_ms),
                   timeout=CONTROL_TIMEOUT)

        def _stop():
            self._send("lego.unsubscribe", channel, timeout=CONTROL_TIMEOUT)
            try:
                Bridge.unprovide(channel)
            except Exception:
                pass

        return _stop

    # --- every device has a button light, a speaker, and an e-stop ---

    def light(self, color="blue", pattern="LIGHT_PATTERN_SOLID", intensity=100):
        return self.call("light_color", _color_const(color), pattern=pattern, intensity=intensity)

    def beep(self, pattern="SOUND_PATTERN_BEEP_SINGLE", frequency=440):
        return self.call("beep", pattern=pattern, frequency=frequency)

    def stop_beep(self):
        return self.call("stop_beep")

    def emergency_stop(self):
        """Skips the device's request queue. Best-effort -- cut power for a
        genuine runaway rather than relying on this."""
        return self._send("lego.estop", timeout=CONTROL_TIMEOUT)

    # --- batching: queue commands into one BLE packet so they start together ---

    def begin_batch(self):
        return self.call("begin_batch")

    def end_batch(self):
        return self.call("end_batch")

    def cancel_batch(self):
        return self.call("cancel_batch")


class SingleMotor(_Device):
    _le_class = "SingleMotor"

    def run(self, speed=50, clockwise=True, wait=True, on_done=None):
        return self.call("motor_run", direction=_spin(clockwise), speed=speed,
                         wait=wait, on_done=on_done)

    def run_for_degrees(self, degrees, clockwise=True, speed=50, wait=True, on_done=None):
        return self.call("motor_run_for_degrees", degrees, direction=_spin(clockwise),
                         speed=speed, wait=wait, on_done=on_done)

    def run_for_time(self, time_ms, clockwise=True, speed=50, wait=True, on_done=None):
        return self.call("motor_run_for_time", time_ms, direction=_spin(clockwise),
                         speed=speed, wait=wait, on_done=on_done)

    def set_speed(self, speed):
        return self.call("motor_set_speed", speed)

    def stop(self):
        return self.call("motor_stop")

    # Signatures below aren't fully documented by LEGO -- forwarded as-is.
    # Use describe() to check the real names if one errors.
    def run_to_absolute_position(self, position, wait=True, on_done=None, **kwargs):
        return self.call("motor_run_to_absolute_position", position,
                         wait=wait, on_done=on_done, **kwargs)

    def run_to_relative_position(self, position, wait=True, on_done=None, **kwargs):
        return self.call("motor_run_to_relative_position", position,
                         wait=wait, on_done=on_done, **kwargs)

    def reset_relative_position(self, position=0):
        return self.call("motor_reset_relative_position", position)

    def set_duty_cycle(self, duty_cycle):
        return self.call("motor_set_duty_cycle", duty_cycle)

    def set_end_state(self, end_state):
        return self.call("motor_set_end_state", end_state)

    def set_acceleration(self, **kwargs):
        return self.call("motor_set_acceleration", **kwargs)

    @property
    def position(self):
        return self.read("motor.position")

    def motor_data(self):
        """motorState, absolutePosition, power, speed, position, gesture."""
        return self.read("motor")


class DoubleMotor(_Device):
    _le_class = "DoubleMotor"

    def run(self, side="MOTOR_BOTH", speed=50, clockwise=True, wait=True, on_done=None):
        return self.call("motor_run", direction=_spin(clockwise), motor=side,
                         speed=speed, wait=wait, on_done=on_done)

    def run_for_degrees(self, degrees, side="MOTOR_BOTH", clockwise=True, speed=50,
                        wait=True, on_done=None):
        return self.call("motor_run_for_degrees", degrees, motor=side,
                         direction=_spin(clockwise), speed=speed, wait=wait, on_done=on_done)

    def run_for_time(self, time_ms, side="MOTOR_BOTH", wait=True, on_done=None, **kwargs):
        return self.call("motor_run_for_time", time_ms, motor=side,
                         wait=wait, on_done=on_done, **kwargs)

    def stop(self, side="MOTOR_BOTH"):
        return self.call("motor_stop", motor=side)

    def move_for_time(self, time_ms, forward=True, speed=50, wait=True, on_done=None):
        return self.call("movement_move_for_time", time_ms=time_ms,
                         direction=_FORWARD if forward else _BACKWARD,
                         speed=speed, wait=wait, on_done=on_done)

    def move_for_degrees(self, degrees, forward=True, speed=50, wait=True, on_done=None):
        return self.call("movement_move_for_degrees", degrees,
                         direction=_FORWARD if forward else _BACKWARD,
                         speed=speed, wait=wait, on_done=on_done)

    def turn_for_degrees(self, degrees, left=True, wait=True, on_done=None):
        """Physically drives the robot -- needs open floor space. Yaw is reset
        first: turning is measured against the IMU, and without a zeroed
        reference the firmware never recognizes 'target reached'."""
        self.call("imu_reset_yaw_axis", 0)
        return self.call("movement_turn_for_degrees", degrees,
                         direction=_TURN_LEFT if left else _TURN_RIGHT,
                         wait=wait, on_done=on_done)

    def imu_reset_yaw(self, value=0):
        return self.call("imu_reset_yaw_axis", value)

    def imu_set_yaw_face(self, face):
        return self.call("imu_set_yaw_face", yaw_face=face)

    def motor_data(self, side="MOTOR_LEFT"):
        """Per-side: motorBitMask, motorState, absolutePosition, power, speed,
        position, gesture."""
        return self.read("motor", index=side)

    def imu_data(self):
        """orientation, yawFace, yaw, pitch, roll, accelerometer/gyroscope XYZ."""
        return self.read("imu_device")

    def imu_gesture_data(self):
        return self.read("imu_gesture")


class ColorSensor(_Device):
    _le_class = "ColorSensor"

    @property
    def color(self):
        return self.read("sensor.color")

    def sensor_data(self):
        """color, reflection, rawRed, rawGreen, rawBlue, hue, saturation, value."""
        return self.read("sensor")


class Controller(_Device):
    _le_class = "Controller"

    def sensor_data(self):
        """leftPercent, rightPercent, leftAngle, rightAngle."""
        return self.read("sensor")
