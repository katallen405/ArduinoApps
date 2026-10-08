import threading
import time
import Audio Classification 
from arduino.app_utils import App

import lelib
from lelib import doubleMotor

# ── Robot setup (runs once, at import time) ───────────────────────────────
dm = doubleMotor()
dm.connect(card_serial="1127")  # CHANGE TO YOUR CARD'S NUMBER
dm.set_speed(30)


def on_go(label, score):
    print(f"  → GO action here (confidence: {score:.0%})")
    dm.run()


def on_left(label, score):
    print(f"  → LEFT action here (confidence: {score:.0%})")
    dm.turn_left(90)


def on_right(label, score):
    print(f"  → RIGHT action here (confidence: {score:.0%})")
    dm.turn_right(90)


def on_stop(label, score):
    print(f"  → STOP action here (confidence: {score:.0%})")
    dm.stop()


callbacks = {
    "Go":    on_go,
    "Left":  on_left,
    "Right": on_right,
    "Stop":  on_stop,
}


# ── Keyword spotting runs in the background ───────────────────────────────
# recognize.start() blocks forever with its own internal loop, so it can't
# be called from user_loop() (the App framework calls user_loop() repeatedly
# and needs it to return quickly each time). Instead we run it in a daemon
# thread and let App.run() own the main thread, as the framework expects.
def _run_recognition():
    while True:
        try:
            recognize.start(callbacks)
        except Exception as e:
            print(f"Recognition error: {e} — restarting in 2s...")
            time.sleep(2)


_recognition_thread = threading.Thread(target=_run_recognition, daemon=True)
_recognition_thread.start()


def loop():
    """Called repeatedly by the App framework. The real work happens in the
    background recognition thread started above; this just keeps the app
    alive and gives the framework a heartbeat."""
    time.sleep(10)


# See: https://docs.arduino.cc/software/app-lab/tutorials/getting-started/#app-run
App.run(user_loop=loop)