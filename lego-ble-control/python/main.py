'''from lego import SingleMotor

#motor = SingleMotor(card_color="azure", card_serial="3683")
motor = SingleMotor()   # no card_color, no card_serial
motor.run_for_degrees(180, speed=60)
print(motor.position)
motor.stop()
'''

from test_hardware import run_all

if __name__ == "__main__":
    run_all()
