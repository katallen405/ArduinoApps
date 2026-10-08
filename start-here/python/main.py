################################################
#Welcome to a new Arduino + Lego Education App!
#This general purpose template will help you get started.



######################IMPORTS######################
#This is where you should put any python packages you want
#to import. Importing packages can give you additional 
#functions that make whatever you're trying to do easier.
#The libraries already here are all you need to control lego 
#motors using the Arduino UNO Q
from arduino.app_utils import *
import lelib as le
from lelib import singleMotor, doubleMotor, colorSensor, controller
##################################################


print("App started, attempting to connect...")
##############CONNECTING TO YOUR HARDWARE###########
#To connect to new hardware, declare an object to give it
#a short name. After, use that name and the connect() 
#function to connect it to your arduino.

#You should make your motor/sensor objects here. Give them a name,
#then assign them a type (le.singleMotor(), le.doubleMotor(), 
# le.colorSensor(), le.controller)
#ex:
#myMotor = le.singleMotor()

YOUR CODE HERE


#Next use the connect function and your connection card's
#serial number to connect the UNO Q to to your hardware
#ex:
#myMotor.connect(card_serial="1151")

YOUR CODE HERE

#####################################################

#############INTERACTING WITH YOUR HARDWARE##########
#This is where you place your code to control the motors/
#sensors. FOR A LIST OF FUNCTIONS FOR EACH DEVICE, OPEN
#README.md ON THE LEFT
#ex
#myMotor.spin(1) 



YOUR CODE HERE




#################DISCONNECT HARDWARE################
#This step is necessary to make new runs of the code work as
#expected.
#ex:
#myMotor.disconnect()

YOUR CODE HERE

exit(0) # successful execution

#Leave this here
App.run()