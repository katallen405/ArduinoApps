# 🥅 Goal-keeper

First-person goalkeeper bot. A front-facing camera color-tracks the orange
ping-pong ball, a Kalman filter predicts where it's going, and one **DoubleMotor**
slides the keeper along its goal line to stay in the ball's path. **No machine
learning** — fast HSV color detection only.

## How it works
camera → HSV detect orange ball → Kalman filter (predict) → error = predicted ball
x − image center → drive the DoubleMotor (both motors together = slide) to zero the
error. Keep the ball centered in view → keeper is in its path. Depth is NOT needed
for a slider, so it's left out.

## Files (python/)
| File | Purpose |
|------|---------|
| `main.py` | App entry point (runs on the UNO Q): camera → keeper → DoubleMotor |
| `keeper.py` | Control logic (`KeeperController`): detect + Kalman + command. No camera/motor. |
| `kalman.py` | The Kalman filter |
| `webcam_test.py` | Laptop test: webcam + on-screen overlay + HSV tuning sliders |
| `hsv_config.json` | Orange ball color range (tune with webcam_test.py) |
| `legoeducation.py`, `lelib.py` | LEGO bridge client (unchanged) |

## Test order

**1. Filter self-test (no camera):**
```bash
python3 kalman.py
```

**2. Laptop webcam test (no board, no motor):**
```bash
pip install opencv-python numpy
python3 webcam_test.py            # add --cam 1 if wrong camera; --synthetic for no cam
```
Move an orange object across the view. Green = ball, blue arrow = prediction, and
the on-screen text shows the slider command (flips sign as the ball crosses center).
Press `t` for HSV sliders, tune until only the ball shows in the "mask" window,
press `s` to save to `hsv_config.json`.

**3. On the board (bridge connected, camera plugged in):**
Edit `main.py`:
- `SOURCE = "camera"`, keep `DRY_RUN = True` first → run the App, watch it print
  `tank=(..)` commands reacting to the ball (no motion).
- Set `MOTOR_COLOR` to the DoubleMotor's colored card, then `DRY_RUN = False`.
Start it:
```bash
arduino-app-cli app start "/home/arduino/ArduinoApps/Goal-keeper"
```

## Motor notes (DoubleMotor slider)
- The slider is ONE DoubleMotor (two motors, one card). We translate by running
  both together (`movement_move_tank(cmd, cmd)`).
- If the keeper slides the WRONG way overall → set `MOTOR_SIGN = -1`.
- If the keeper ROTATES instead of sliding (the two motors oppose each other) →
  set `RIGHT_SIGN = -1` to flip one side.

## Tuning (top of main.py / keeper.py)
- `KP` — reaction strength (higher = snappier, riskier to overshoot)
- `DEADBAND_PX` — dead zone so it doesn't jitter when centered
- `LOOKAHEAD` — how many frames ahead the Kalman filter predicts
- `MAX_SPEED` — motor speed cap
- Kalman `process_var` / `measurement_var` in kalman.py — smoothing vs. responsiveness

## Known limit
A slow slider can't fully catch a very fast side-to-side ball — prediction helps but
the motor's top speed is the ceiling. Retune the ball color for the keeper's own
lighting; the first-person view differs from the overhead camera.
