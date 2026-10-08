"""
LEGO Education BLE agent -- runs inside the `lego-ble` sidecar container.

This is the only process with access to the host's Bluetooth stack (via the
D-Bus socket bind-mounted in brick_compose.yaml). It exposes legoeducation to
the `main` app container over Arduino's msgpack-RPC router.

Wire protocol (msgpack arrays):
    [0, msgid, method, params]   request
    [1, msgid, error, result]    response
    [2, method, params]          notify (fire-and-forget; used for push data)
"""

import concurrent.futures
import json
import os
import signal
import socket
import threading
import time

import msgpack
import legoeducation as le

SOCKET_PATH = os.environ.get("ROUTER_SOCKET", "/run/arduino-router.sock")

# Shutdown must finish well inside Docker's ~10s SIGTERM -> SIGKILL window,
# or the container gets force-killed (exit 137) with devices still connected.
SHUTDOWN_GRACE_SECONDS = 5.0

_devices = {}          # device key -> legoeducation device object
_subscriptions = {}    # device key -> {channel: {"min_interval": float, "last": {type: ts}}}
_state_lock = threading.RLock()

_executors = {}        # device key -> single-thread executor
_executors_lock = threading.Lock()

_send_lock = threading.Lock()
_conn = {"sock": None}


def _key(device_class, connect_kwargs):
    return (device_class, tuple(sorted(connect_kwargs.items())))


def _executor_for(k):
    """One dedicated worker thread per physical device. Calls to a given device
    always run on the same thread (legoeducation's async worker expects
    consistent thread context), while different devices run in parallel."""
    with _executors_lock:
        ex = _executors.get(k)
        if ex is None:
            ex = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"dev-{k[0]}"
            )
            _executors[k] = ex
        return ex


def _resolve(value):
    """Map strings like 'MOTOR_MOVE_DIRECTION_CLOCKWISE' onto library constants.
    Raises on an unknown constant rather than passing the raw string through --
    silently handing bad values to hardware control is worse than failing."""
    if isinstance(value, str) and value.isupper():
        if not hasattr(le, value):
            raise ValueError(
                f"'{value}' looks like a constant but legoeducation has no such "
                f"attribute -- check spelling or installed package version"
            )
        return getattr(le, value)
    return value


def _resolve_all(args, kwargs):
    return [_resolve(a) for a in args], {k: _resolve(v) for k, v in kwargs.items()}


def _device(device_class, connect_kwargs):
    k = _key(device_class, connect_kwargs)
    with _state_lock:
        dev = _devices.get(k)
        if dev is None:
            dev = getattr(le, device_class)()
            _devices[k] = dev
    if not dev.connected:
        _, kwargs = _resolve_all((), connect_kwargs)
        dev.connect(**kwargs)
    return dev


def _jsonable(obj):
    """Fallback encoder for legoeducation's custom result/data objects."""
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return str(obj)


def _to_json(value):
    return json.dumps(value, default=_jsonable)


def _plain(value):
    """Any legoeducation object graph -> plain msgpack-safe data."""
    return json.loads(_to_json(value))


def _send(msg):
    sock = _conn["sock"]
    if sock is None:
        return
    with _send_lock:
        try:
            sock.sendall(msgpack.packb(msg, use_bin_type=True))
        except OSError:
            pass


# --- queued handlers: run on the target device's own worker thread ---

def _lego_connect(device_class, connect_kwargs):
    return _to_json(bool(_device(device_class, connect_kwargs).connected))


def _lego_disconnect(device_class, connect_kwargs):
    k = _key(device_class, connect_kwargs)
    with _state_lock:
        dev = _devices.pop(k, None)
        _subscriptions.pop(k, None)
    if dev is not None:
        dev.disconnect()
    return _to_json(True)


def _lego_call(device_class, connect_kwargs, method, args, kwargs):
    dev = _device(device_class, connect_kwargs)
    a, kw = _resolve_all(args, kwargs)
    return _to_json(getattr(dev, method)(*a, **kw))


def _lego_get(device_class, connect_kwargs, path, index=None):
    dev = _device(device_class, connect_kwargs)
    parts = path.split(".")
    obj = getattr(dev, parts[0])
    if index is not None:
        obj = obj[_resolve(index)]        # e.g. dev.motor[le.MOTOR_LEFT]
    for part in parts[1:]:
        obj = getattr(obj, part)
    return _to_json(obj)


def _lego_describe(device_class, connect_kwargs):
    """Public methods/attributes of the real legoeducation object -- lets the
    app side discover functions this brick doesn't wrap by name."""
    dev = _device(device_class, connect_kwargs)
    return _to_json(sorted(n for n in dir(dev) if not n.startswith("_")))


def _lego_notification_rate(device_class, connect_kwargs, delay_ms):
    """Hardware-side notification rate. 0 = off, otherwise 15..1000 ms."""
    dev = _device(device_class, connect_kwargs)
    dev.device_notification_request(int(delay_ms))
    return _to_json(True)


def _lego_subscribe(device_class, connect_kwargs, channel, min_interval=0.0, rate_ms=None):
    """Bridge legoeducation's streaming callback to notify frames.

    rate_ms sets the hardware's own reporting interval (0 = off, else 15..1000).
    min_interval (seconds, 0 = unthrottled) additionally caps callbacks per
    notification type on this side, before JSON encoding, so dropped events
    cost essentially nothing.
    """
    dev = _device(device_class, connect_kwargs)
    k = _key(device_class, connect_kwargs)
    with _state_lock:
        _subscriptions.setdefault(k, {})[channel] = {
            "min_interval": float(min_interval or 0.0),
            "last": {},
        }

    def _on_notification(raw):
        try:
            items = le.device_notification_parser(raw)
        except Exception:
            return
        now = time.monotonic()
        for item in items:
            kind = type(item).__name__
            payload = None
            with _state_lock:
                targets = list(_subscriptions.get(k, {}).items())
            for ch, cfg in targets:
                gap = cfg["min_interval"]
                if gap:
                    if now - cfg["last"].get(kind, 0.0) < gap:
                        continue
                    cfg["last"][kind] = now
                if payload is None:              # encoded lazily, only if sending
                    payload = _plain(item)
                    payload["_type"] = kind
                _send([2, ch, [payload]])

    dev.set_notification_callback(_on_notification)
    if rate_ms is not None:
        dev.device_notification_request(int(rate_ms))
    return _to_json(True)


# --- immediate handlers: bypass the device queue entirely ---

def _lego_call_async(device_class, connect_kwargs, method, args, kwargs, channel):
    """Dispatch a long-running call and return at once. The result arrives
    later on `channel` as {'ok': True, 'result': ...} or {'ok': False, 'error': ...}."""
    k = _key(device_class, connect_kwargs)

    def _run():
        try:
            dev = _device(device_class, connect_kwargs)
            a, kw = _resolve_all(args, kwargs)
            _send([2, channel, [{"ok": True, "result": _plain(getattr(dev, method)(*a, **kw))}]])
        except Exception as exc:
            _send([2, channel, [{"ok": False, "error": f"{type(exc).__name__}: {exc}"}]])

    _executor_for(k).submit(_run)
    return _to_json(True)      # "dispatched", not "finished"


def _lego_unsubscribe(device_class, connect_kwargs, channel):
    k = _key(device_class, connect_kwargs)
    with _state_lock:
        channels = _subscriptions.get(k)
        if channels:
            channels.pop(channel, None)
    return _to_json(True)


def _lego_estop(device_class, connect_kwargs):
    """Emergency stop. Never queues -- must not wait behind a wedged call.
    Best-effort: legoeducation makes no promise about calling into a device
    while another thread has it mid-call. Cut power for a real runaway."""
    k = _key(device_class, connect_kwargs)
    with _state_lock:
        dev = _devices.get(k)
    if dev is None:
        return _to_json(False)
    for name in ("motor_stop", "movement_stop"):
        fn = getattr(dev, name, None)
        if fn is None:
            continue
        try:
            fn()
        except Exception:
            pass
    return _to_json(True)


QUEUED_HANDLERS = {
    "lego.connect": _lego_connect,
    "lego.disconnect": _lego_disconnect,
    "lego.call": _lego_call,
    "lego.get": _lego_get,
    "lego.describe": _lego_describe,
    "lego.notification_rate": _lego_notification_rate,
    "lego.subscribe": _lego_subscribe,
}

IMMEDIATE_HANDLERS = {
    "lego.call_async": _lego_call_async,
    "lego.unsubscribe": _lego_unsubscribe,
    "lego.estop": _lego_estop,
}

HANDLERS = {**QUEUED_HANDLERS, **IMMEDIATE_HANDLERS}


def _cleanup(signum, frame):
    """Release every BLE connection, bounded. Uses fresh threads rather than
    the per-device executors -- those may be blocked by whatever wedged call
    triggered the shutdown in the first place."""
    with _state_lock:
        devices = list(_devices.values())
        _devices.clear()
        _subscriptions.clear()

    def _disconnect(dev):
        try:
            dev.disconnect()
        except Exception:
            pass

    threads = []
    for dev in devices:
        t = threading.Thread(target=_disconnect, args=(dev,), daemon=True)
        t.start()
        threads.append(t)

    deadline = time.monotonic() + SHUTDOWN_GRACE_SECONDS
    for t in threads:
        t.join(timeout=max(0.0, deadline - time.monotonic()))

    raise SystemExit(0)


def _dispatch(msgid, method, params):
    fn = HANDLERS.get(method)
    if fn is None:
        _send([1, msgid, [1, f"no such method: {method}"], None])
        return
    try:
        if method in IMMEDIATE_HANDLERS:
            result = fn(*params)
        else:
            result = _executor_for(_key(params[0], params[1])).submit(fn, *params).result()
        _send([1, msgid, None, result])
    except Exception as exc:
        _send([1, msgid, [1, f"{type(exc).__name__}: {exc}"], None])


def _handle(msg):
    if msg[0] != 0:        # ignore anything that isn't an incoming request
        return
    _, msgid, method, params = msg
    threading.Thread(target=_dispatch, args=(msgid, method, params), daemon=True).start()


def session():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_PATH)
    _conn["sock"] = sock
    print(f"connected to router at {SOCKET_PATH}", flush=True)
    try:
        unpacker = msgpack.Unpacker(raw=False)

        # One registration at a time, waiting for each confirmation. Firing
        # them all at once caused the router to silently drop some.
        for msgid, name in enumerate(HANDLERS):
            _send([0, msgid, "$/register", [name]])
            confirmed = False
            while not confirmed:
                data = sock.recv(4096)
                if not data:
                    print("router closed the connection during registration", flush=True)
                    return
                unpacker.feed(data)
                for msg in unpacker:
                    if msg[0] == 1 and msg[1] == msgid:
                        confirmed = True
                    else:
                        _handle(msg)     # don't drop requests arriving mid-registration
            print(f"registered {name}", flush=True)

        print(f"all {len(HANDLERS)} methods registered", flush=True)

        while True:
            data = sock.recv(4096)
            if not data:
                print("router closed the connection", flush=True)
                return
            unpacker.feed(data)
            for msg in unpacker:
                _handle(msg)
    finally:
        _conn["sock"] = None
        try:
            sock.close()
        except OSError:
            pass


def main():
    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)
    while True:
        try:
            session()
        except OSError as exc:      # covers FileNotFound/ConnectionRefused/Reset
            print(f"waiting for router: {exc}", flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
