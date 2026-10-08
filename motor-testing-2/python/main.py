from lego import DoubleMotor, LegoError

print("App started, attempting to connect...")

# card_color/card_serial go in the constructor -- connect() takes no arguments.
doublemotor = DoubleMotor(card_serial="0026")

doublemotor.connect()

if not doublemotor.connected:
    print('Error connecting to Double Motor.')
    exit(1)

# "MOTOR_BOTH" is the default side, so this runs both motors together
# for one full rotation.
doublemotor.run_for_degrees(360)

doublemotor.disconnect()
exit(0)