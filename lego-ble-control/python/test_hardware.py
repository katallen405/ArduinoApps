"""
Hardware integration tests for the LEGO Education brick.

These are physical integration tests, not mocked unit tests -- a PASS means
real hardware responded over BLE. Devices that aren't present are skipped,
not failed. Some tests physically move motors; give them clear space.
"""

import time
import unittest

from lego import SingleMotor, DoubleMotor, ColorSensor, Controller, LegoError

# Fill in to target a specific unit via its Connection Card. Only needed when
# you have two devices of the same class; different classes disambiguate
# automatically.
SINGLE_MOTOR_CARD = dict(card_color=None, card_serial=None)
DOUBLE_MOTOR_CARD = dict(card_color="green", card_serial="0026")
COLOR_SENSOR_CARD = dict(card_color=None, card_serial=None)
CONTROLLER_CARD   = dict(card_color=None, card_serial=None)


def _card_kwargs(card):
    return {k: v for k, v in card.items() if v}


def _connect_or_skip(test_case, device):
    try:
        ok = device.connect()
    except LegoError as exc:
        test_case.skipTest(f"connect() raised: {exc}")
        return
    if not ok:
        test_case.skipTest("device not found -- is it powered on and broadcasting?")


def _release(device, stop=False):
    """Best-effort teardown. Never raises -- a failure here would mask the
    real test result, and a leaked BLE connection blocks the next run."""
    if device is None:
        return
    if stop:
        try:
            device.stop()
        except Exception:
            pass
    try:
        device.disconnect()
    except Exception:
        pass


class SingleMotorTest(unittest.TestCase):
    def setUp(self):
        self.motor = SingleMotor(**_card_kwargs(SINGLE_MOTOR_CARD))
        _connect_or_skip(self, self.motor)

    def tearDown(self):
        _release(getattr(self, "motor", None), stop=True)

    def test_connected(self):
        self.assertTrue(self.motor.connected)

    def test_run_for_degrees_changes_position(self):
        start = self.motor.position
        self.motor.run_for_degrees(90, speed=40)
        time.sleep(1.5)
        self.assertNotEqual(start, self.motor.position,
                            "position didn't change after a 90-degree run")

    def test_motor_data_shape(self):
        data = self.motor.motor_data()
        for field in ("motorState", "absolutePosition", "power", "speed", "position", "gesture"):
            self.assertIn(field, data)

    def test_notifications_arrive(self):
        received = []
        stop = self.motor.on_update(received.append, rate_ms=50)
        try:
            self.motor.run_for_degrees(180, speed=40)
            time.sleep(1.0)
        finally:
            stop()
        self.assertTrue(received, "no notifications arrived while the motor ran")

    def test_light_and_beep_do_not_raise(self):
        self.motor.light("green")
        self.motor.beep()


class DoubleMotorTest(unittest.TestCase):
    def setUp(self):
        self.motor = DoubleMotor(**_card_kwargs(DOUBLE_MOTOR_CARD))
        _connect_or_skip(self, self.motor)

    def tearDown(self):
        _release(getattr(self, "motor", None), stop=True)

    def test_connected(self):
        self.assertTrue(self.motor.connected)

    def test_move_for_degrees_changes_position(self):
        start = self.motor.motor_data("MOTOR_LEFT")["position"]
        self.motor.move_for_degrees(90, forward=True, speed=40)
        time.sleep(1.5)
        self.assertNotEqual(start, self.motor.motor_data("MOTOR_LEFT")["position"])

    def test_turn_for_degrees_does_not_raise(self):
        # Physically drives the robot in a turn -- needs open floor space.
        # Turning is relative and hard to assert on, so this just confirms
        # the call completes against real hardware.
        self.motor.turn_for_degrees(45, left=True)
        time.sleep(1.0)

    def test_imu_data_shape(self):
        data = self.motor.imu_data()
        for field in ("yaw", "pitch", "roll", "accelerometerX", "gyroscopeX"):
            self.assertIn(field, data)

    def test_light_and_beep_do_not_raise(self):
        self.motor.light("blue")
        self.motor.beep()


class ColorSensorTest(unittest.TestCase):
    def setUp(self):
        self.sensor = ColorSensor(**_card_kwargs(COLOR_SENSOR_CARD))
        _connect_or_skip(self, self.sensor)

    def tearDown(self):
        _release(getattr(self, "sensor", None))

    def test_connected(self):
        self.assertTrue(self.sensor.connected)

    def test_sensor_data_shape(self):
        data = self.sensor.sensor_data()
        for field in ("color", "reflection", "rawRed", "rawGreen", "rawBlue",
                      "hue", "saturation", "value"):
            self.assertIn(field, data)

    def test_color_property_returns_a_value(self):
        # Can't assert a specific color without knowing what's in front of the
        # sensor -- this confirms the read pipeline works.
        self.assertIsNotNone(self.sensor.color)

    def test_notification_rate_is_accepted(self):
        self.sensor.set_notification_rate(200)
        self.sensor.set_notification_rate(0)     # off again
        with self.assertRaises(ValueError):
            self.sensor.set_notification_rate(5)  # below the 15ms floor

    def test_light_and_beep_do_not_raise(self):
        self.sensor.light("red")
        self.sensor.beep()


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.controller = Controller(**_card_kwargs(CONTROLLER_CARD))
        _connect_or_skip(self, self.controller)

    def tearDown(self):
        _release(getattr(self, "controller", None))

    def test_connected(self):
        self.assertTrue(self.controller.connected)

    def test_sensor_data_shape(self):
        data = self.controller.sensor_data()
        for field in ("leftPercent", "rightPercent", "leftAngle", "rightAngle"):
            self.assertIn(field, data)

    def test_light_and_beep_do_not_raise(self):
        self.controller.light("purple")
        self.controller.beep()


def run_all():
    """Entry point for App Lab -- prints a standard unittest summary."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for case in (SingleMotorTest, DoubleMotorTest, ColorSensorTest, ControllerTest):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    unittest.main()
