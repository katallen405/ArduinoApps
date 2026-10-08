"""
webcam_test.py — test the goalkeeper on a laptop webcam (no board, no motor).

Shows the ball (green), the Kalman prediction (blue arrow), the image center line,
and the slider command the keeper WOULD send. Move an orange object across the view
and watch the command flip sign as the ball crosses center.

    pip install opencv-python numpy
    python3 webcam_test.py            # add --cam 1 if the wrong camera opens
    python3 webcam_test.py --synthetic

KEYS (focus the video window):
    q = quit
    t = show/hide HSV tuning sliders
    s = save the HSV range to hsv_config.json (so main.py uses it on the board)
"""

import argparse
import json
import os
import time

import cv2
import numpy as np

from keeper import KeeperController, HSV_PATH, load_hsv

_synth_t = 0
_synth_keeper_world = None
HSV = {}


def synthetic_frame(w, h):
    global _synth_t, _synth_keeper_world
    if _synth_keeper_world is None:
        _synth_keeper_world = w / 2
    frame = np.full((h, w, 3), 40, np.uint8)
    center = w / 2
    phase = (_synth_t % 150) / 150.0
    tri = 1 - abs(2 * phase - 1)
    ball_world = 60 + tri * (w - 120)
    image_x = center + (ball_world - _synth_keeper_world)
    if 0 <= image_x <= w:
        cv2.circle(frame, (int(image_x), int(h * 0.45)), 20, (0, 140, 255), -1)
    cv2.rectangle(frame, (int(center) - 40, h - 40), (int(center) + 40, h - 15),
                  (0, 200, 0), -1)
    _synth_t += 1
    return frame


def make_sliders(ctrl):
    global HSV
    lo, hi = ctrl.lo, ctrl.hi
    HSV = {"h_lo": int(lo[0]), "s_lo": int(lo[1]), "v_lo": int(lo[2]),
           "h_hi": int(hi[0]), "s_hi": int(hi[1]), "v_hi": int(hi[2])}
    cv2.namedWindow("tuning", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("tuning", 400, 260)
    for name, mx in [("h_lo", 179), ("h_hi", 179), ("s_lo", 255),
                     ("s_hi", 255), ("v_lo", 255), ("v_hi", 255)]:
        cv2.createTrackbar(name, "tuning", HSV[name], mx, lambda v: None)


def read_sliders(ctrl):
    for n in HSV:
        HSV[n] = cv2.getTrackbarPos(n, "tuning")
    ctrl.lo = np.array([HSV["h_lo"], HSV["s_lo"], HSV["v_lo"]])
    ctrl.hi = np.array([HSV["h_hi"], HSV["s_hi"], HSV["v_hi"]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--cam", type=int, default=0)
    args = ap.parse_args()

    ctrl = KeeperController()
    synth = args.synthetic
    cap = None
    if not synth:
        cap = cv2.VideoCapture(args.cam)
        if not cap.isOpened():
            print("Could not open webcam. Try --cam 1 or --synthetic.")
            return
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    else:
        w, h = 1280, 720

    show_sliders = False
    print("Goalkeeper webcam test. Keys: q quit | t sliders | s save HSV")
    while True:
        frame = synthetic_frame(w, h) if synth else cap.read()[1]
        if frame is None:
            continue
        if show_sliders:
            read_sliders(ctrl)
        r = ctrl.process(frame)
        ctrl.draw(frame, r)
        cv2.imshow("goalkeeper webcam test (q quit)", frame)
        if show_sliders:
            mask = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), ctrl.lo, ctrl.hi)
            cv2.imshow("mask", mask)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("t"):
            show_sliders = not show_sliders
            if show_sliders:
                make_sliders(ctrl)
            else:
                cv2.destroyWindow("tuning")
        elif key == ord("s"):
            cfg = {"ball": {k: int(v) for k, v in HSV.items()}} if HSV else None
            if cfg:
                json.dump(cfg, open(HSV_PATH, "w"), indent=2)
                print(f"saved -> {HSV_PATH}: {cfg}")
            else:
                print("open sliders with 't' first, then 's' to save")

    if cap:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
