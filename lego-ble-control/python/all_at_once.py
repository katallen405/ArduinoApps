from lego import SingleMotor, DoubleMotor, ColorSensor, Controller
import time

motor = SingleMotor()
dm = DoubleMotor()
cs = ColorSensor()
ctl = Controller()

for device, name in [(motor, "SingleMotor"), (dm, "DoubleMotor"), (cs, "ColorSensor"), (ctl, "Controller")]:
    print(name, "connected:", device.connected)

# Prove they're all genuinely live at once, not just sequentially connected
print("motor position:", motor.position)
print("dm left position:", dm.motor_data("MOTOR_LEFT")["position"])
print("color:", cs.color)
print("controller:", ctl.sensor_data())

time.sleep(2)

for device in (motor, dm, cs, ctl):
    device.disconnect()