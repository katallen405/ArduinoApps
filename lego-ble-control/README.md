# LEGO Education BLE Brick

Custom Arduino App Lab brick that controls LEGO Education hardware (Single Motor,
Double Motor, Color Sensor, Controller) over Bluetooth LE, from Python running on
the UNO Q.

## Why this brick exists

The `main` app container that runs `main.py` has no Bluetooth/D-Bus access and
can't be modified directly — it's a fixed image App Lab controls. So this brick
runs BLE code in a **second container** ("the sidecar," service name `lego-ble`)
that *does* have D-Bus access, and talks to it from `main.py` over Arduino's
built-in msgpack-RPC router (the same `Bridge` used for MCU communication).

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│   main container            │  RPC   │   lego-ble container         │
│   (uid 1000, fixed image)   │◄──────►│   (root, built from our      │
│                             │ router │    own Dockerfile)           │
│   main.py                   │        │                              │
│   bricks/lego/__init__.py   │        │   service/agent.py           │
│   (thin RPC proxy)          │        │   (real legoeducation+bleak, │
│                             │        │    talks to host D-Bus/BlueZ)│
└─────────────────────────────┘        └──────────────────────────────┘
```

`__init__.py` never touches Bluetooth directly — every call it makes is a
request over the router to `agent.py`, which is the only place `legoeducation`
and `bleak` are actually installed and used.

## File map

```
bricks/lego/
├── brick_config.yaml       # brick identity (id: lego) -- must match app.yaml
├── brick_compose.yaml      # declares the lego-ble sidecar container
├── __init__.py             # RPC proxy classes -- runs in `main`
└── service/
    ├── Dockerfile          # builds the sidecar image
    └── agent.py            # real legoeducation/bleak code -- runs in lego-ble
```

`app.yaml` at the project root must reference the brick by its `id`:
```yaml
bricks:
- lego: {}
```

## Building and rebuilding the sidecar

App Lab does **not** build Docker images for you (`build:` isn't supported in
`brick_compose.yaml`) — the image is built by hand, once, and referenced by tag:

```bash
cd ArduinoApps/<your-app>/bricks/lego/service
docker build -t lego-ble:1 .
```

**Rebuild whenever `agent.py` or the `Dockerfile` changes.** Changes to
`__init__.py` need **no rebuild** — it's plain Python read fresh by `main` on
every Run, not baked into an image.

After rebuilding, if a container from the *old* image is still running, Compose
won't automatically replace it. Force a fresh one:
```bash
docker stop <app-name>-lego-ble-1
docker rm <app-name>-lego-ble-1
```
Then hit Run in App Lab again.

## Quick start — all four devices

```python
from lego import SingleMotor, DoubleMotor, ColorSensor, Controller

motor = SingleMotor()
motor.run_for_degrees(180, speed=60)
print(motor.position)
motor.disconnect()

dm = DoubleMotor()
dm.move_for_degrees(360, forward=True, speed=50)
dm.turn_for_degrees(90, left=True)     # needs open floor space -- physically drives
print(dm.motor_data("MOTOR_LEFT")["position"])
dm.disconnect()

cs = ColorSensor()
print(cs.color)
cs.disconnect()

ctl = Controller()
print(ctl.sensor_data())
ctl.disconnect()
```

Devices connect automatically the first time you call anything on them — no
explicit `.connect()` required (though it's there if you want to check success
up front). Only supply `card_color`/`card_serial` (from the physical Connection
Card) if you have more than one device of the *same* class and need to pick a
specific unit — e.g. `SingleMotor(card_color="azure", card_serial="3683")`.
Different device *classes* (motor vs. sensor vs. controller) never need this;
they disambiguate automatically.

## Shared methods (every device has these)

| Method | What it does |
|---|---|
| `connect()` | Force a connection now; returns `True`/`False`. Not required otherwise. |
| `disconnect()` | Release the BLE connection. **Always call when you're done** — a device only accepts one connection at a time, and a leaked connection blocks anyone else (including a fresh test run) from reaching that hardware. |
| `connected` | Property, `True`/`False`. |
| `call(method, *args, **kwargs)` | Generic escape hatch — invokes *any* method the real `legoeducation` device object has, even ones without a named wrapper below. |
| `read(path, index=None)` | Generic escape hatch — reads *any* attribute, e.g. `read("motor.position")` or `read("motor", index="MOTOR_LEFT")`. |
| `light(color="blue", pattern="LIGHT_PATTERN_SOLID", intensity=100)` | Sets the hub's button light. `color` accepts short names (`"green"`) or full constants (`"LEGO_COLOR_GREEN"`). |
| `beep(pattern="SOUND_PATTERN_BEEP_SINGLE", frequency=440)` | Sounds the hub's speaker. |
| `on_update(handler)` | Subscribes to real-time push updates (see below). Returns a function — call it to unsubscribe. |
| `emergency_stop()` | See **Emergency stop**, below. |

## SingleMotor

```python
motor = SingleMotor()
motor.run_for_degrees(180, clockwise=True, speed=60)
motor.run(speed=40, clockwise=False)
motor.run_for_time(2000, speed=50)          # ms
motor.set_speed(30)
motor.stop()
print(motor.position)                       # shortcut for motor_data()["position"]
print(motor.motor_data())                   # {'motorState', 'absolutePosition', 'power', 'speed', 'position', 'gesture'}
motor.light("azure")
motor.beep()
motor.disconnect()
```

Less-documented functions (LEGO's own docs don't give full signatures for
these — forwarded as-is via `**kwargs`; check `help(le.SingleMotor)` on the
board if a call errors on argument names):
```python
motor.run_to_absolute_position(position, ...)
motor.run_to_relative_position(position, ...)
motor.reset_relative_position(position=0)
motor.set_duty_cycle(duty_cycle)
motor.set_end_state(end_state)              # e.g. "MOTOR_END_STATE_BRAKE"
motor.set_acceleration(...)
```

## DoubleMotor

```python
dm = DoubleMotor()
dm.move_for_time(1500, forward=True, speed=50)
dm.move_for_degrees(360, forward=True, speed=50)
dm.turn_for_degrees(90, left=True)          # physically drives -- open floor space
dm.run(side="MOTOR_LEFT", speed=40, clockwise=True)     # independent single-side control
dm.run_for_degrees(360, side="MOTOR_RIGHT", speed=30)
dm.stop()                                    # side="MOTOR_BOTH" by default

print(dm.motor_data("MOTOR_LEFT"))          # per-side: motorBitMask, motorState, absolutePosition, power, speed, position, gesture
print(dm.imu_data())                        # orientation, yawFace, yaw, pitch, roll, accelerometerX/Y/Z, gyroscopeX/Y/Z
print(dm.imu_gesture_data())

dm.imu_reset_yaw(0)
dm.imu_set_yaw_face("DEVICE_FACE_TOP")
dm.disconnect()
```

> **`turn_for_degrees` resets the yaw axis internally before every call.**
> Turning in place is measured against the IMU's yaw, not just wheel-encoder
> counts — without a zeroed reference point, the firmware never recognizes
> "target reached" and the motors spin indefinitely. This was a real, hard-won
> bug (see **Troubleshooting** below) — the fix is already baked into the
> method, but worth knowing if you ever bypass it via `.call()` directly.

## ColorSensor

```python
cs = ColorSensor()
print(cs.color)                             # shortcut for sensor_data()["color"]
print(cs.sensor_data())                     # color, reflection, rawRed, rawGreen, rawBlue, hue, saturation, value
cs.light("red")
cs.disconnect()
```

## Controller

```python
ctl = Controller()
print(ctl.sensor_data())                    # leftPercent, rightPercent, leftAngle, rightAngle
ctl.disconnect()
```

## Non-blocking calls (`wait=False`)

Some commands run the physical hardware for as long as it takes to finish —
`run_for_degrees`, `move_for_degrees`, `turn_for_degrees`, anything that
actually moves something. By default these **block** until the movement
completes, however long that takes. For a long or unpredictable-duration
command, don't guess at a timeout — dispatch it and get notified when it's
actually done instead:

```python
def on_finished(result):
    print("turn finished:", result)   # {'ok': True, 'result': ...} or {'ok': False, 'error': ...}

dm.turn_for_degrees(720, left=True, wait=False, on_done=on_finished)
print("this prints immediately, motor is still turning")
```

Every motor method that issues a movement accepts `wait=` and `on_done=`.

## Real-time updates (`on_update`)

`legoeducation`'s own streaming notification callback is bridged across the
RPC boundary as push (`notify`) messages — no polling required:

```python
def on_motor_event(data):
    print(data["_type"], "->", data)    # e.g. "MotorNotification" -> {'position': 42, ...}

stop = motor.on_update(on_motor_event)
motor.run_for_degrees(360, speed=40)
import time; time.sleep(5)
stop()                                   # unsubscribe when done
```

**Cost to know about:** each notification is JSON-encoded/decoded crossing the
boundary. Fine for normal use; if you notice lag under very frequent updates
(fast position streaming, for instance), that round-trip is the first place to
look.

## Emergency stop

```python
motor.emergency_stop()
```

Bypasses the normal per-device request queue entirely and tries to stop the
motor immediately, even if another command is currently mid-flight on that
same device. It's best-effort, not guaranteed — calling into a device while
another thread is mid-call isn't something `legoeducation` promises is safe.
**If a motor is genuinely running away and this doesn't stop it fast enough,
cut power to the hub physically.** Software is not a substitute for a hand on
the power button when hardware is actively moving.

## Simultaneous devices

All four device classes can be connected and used at once — each is tracked
independently and gets its own dedicated worker thread, so a slow call on one
device never blocks another. No extra setup needed; just instantiate all four.
One real caveat: the physical BLE radio has some hardware limit on
simultaneous connections that hasn't been precisely characterized on this
board — if you're bringing many devices online at once, add them one at a
time and confirm each connects rather than assuming an arbitrary number will
all work together.

---

## Troubleshooting

### "device not found -- is it powered on and broadcasting?"
The device genuinely wasn't reachable in the scan window. Check power, and
that nothing else (a phone app, the Coding Canvas) is already connected to it
— LEGO Education hardware accepts exactly one BLE connection at a time.

### `Request '...' timed out after Ns`
Either the operation genuinely takes longer than the timeout (raise it:
`motor.call(..., timeout=60)`, or use `wait=False` for movement commands — see
above), or the sidecar/radio is in a bad state (see the two sections below).

### `method '...' not available`
Historically caused by the sidecar registering its six RPC methods with the
router all at once — some got dropped. Already fixed by making registration
synchronous (one at a time, waiting for confirmation) in `agent.py`. If this
resurfaces, check `docker logs <app>-lego-ble-1 | grep registering` — you
should see one line per method, ending in `all methods registered`.

### Motor doesn't release / stays connected after Stop
Caused by the sidecar being force-killed (`SIGKILL`, exit code `137`) before
its shutdown handler finished disconnecting devices. The current `agent.py`
bounds that cleanup to ~5 seconds so it can't hang the shutdown — if you still
see this, check `docker ps -a` for exit code `137` and `docker logs` for
what was in progress when it was killed.

### Duplicate / stale containers
`restart: unless-stopped` means old test containers (from earlier iterations,
different app names) can keep running indefinitely in the background, holding
onto the same BLE hardware or colliding on router method registration.
```bash
docker ps -a --format '{{.Names}}\t{{.Status}}'
```
Anything with `lego-ble` in the name other than your current app's container
is a suspect:
```bash
docker stop <stray-name>
docker rm <stray-name>
```

### Everything times out instantly, or "not found" resolves suspiciously fast
Check the actual Bluetooth radio, outside any container:
```bash
bluetoothctl show
```
Look for `Powered: no`. If so:
```bash
bluetoothctl power on
```
If that fails (`org.bluez.Error.Failed`), check for a deeper driver/firmware
fault:
```bash
sudo dmesg | grep -i -E "blue|hci" | tail -40
```
Lines like `Reading QCA version information failed (-110)` and
`Retry BT power ON:0/1/2` indicate the onboard Bluetooth chip itself failed to
initialize — a known class of issue with this chip family, not specific to
this brick's code. **A full power cycle of the board** (not just a service
restart) is the most reliable recovery.

### Testing the library directly, bypassing everything
When you need to know whether a problem is in this brick's code or in
`legoeducation`/the hardware itself, go straight to the source inside the
sidecar, no RPC involved:
```bash
docker exec -i <app>-lego-ble-1 python3 << 'EOF'
import legoeducation as le
dm = le.DoubleMotor()
dm.connect()
print(dm.connected)
dm.disconnect()
EOF
```
Use `-i` (not `-it`) with a heredoc for multi-line scripts — the interactive
REPL's auto-indent mangles pasted blocks.

---

## Sharing this brick

App Lab's project export/import (zip archive) carries every file above. The
one thing it does **not** carry: the built sidecar image. Whoever receives
this brick must run the build step themselves once, on their own board,
before their first Run:
```bash
cd ArduinoApps/<their-app>/bricks/lego/service
docker build -t lego-ble:1 .
```

**License note:** `legoeducation` is distributed under BUSL-1.1 (Business
Source License), not a standard permissive open-source license. Fine for
personal use; worth reviewing its terms before redistributing this brick
broadly.

