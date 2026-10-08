"""
keeper.py — goalkeeper control logic (no ML). Detects the orange ball by HSV color,
rejects look-alikes (cardboard, yellow, boxes) by requiring a round, ball-sized
blob, tracks it with the Kalman filter, and turns the ball's predicted horizontal
position into a slider motor command.

Pure logic: no camera, no motor code.
"""

import json
import os
from dataclasses import dataclass

import cv2
import numpy as np

from kalman import BallKalman

HERE = os.path.dirname(__file__)
HSV_PATH = os.path.join(HERE, "hsv_config.json")

# orange ping-pong ball default range (tune with webcam_test.py -> hsv_config.json)
BALL_HSV = {"h_lo": 5, "s_lo": 150, "v_lo": 80, "h_hi": 18, "s_hi": 255, "v_hi": 255}


@dataclass
class KeeperResult:
    found: bool
    cmd: int          # slider motor speed, signed (-max..max); + = one way, - = other
    error: float      # predicted ball x minus image center (pixels)
    x: float          # filtered ball x
    y: float
    pred_x: float
    radius: float
    vx: float = 0.0   # ball horizontal velocity (px/frame) — used to pick direction


def load_hsv():
    cfg = dict(BALL_HSV)
    if os.path.exists(HSV_PATH):
        try:
            j = json.load(open(HSV_PATH))
            cfg.update(j.get("ball", j))     # accept {"ball":{...}} or a flat dict
        except Exception as e:
            print(f"[keeper] could not read {HSV_PATH}: {e}")
    lo = np.array([cfg["h_lo"], cfg["s_lo"], cfg["v_lo"]])
    hi = np.array([cfg["h_hi"], cfg["s_hi"], cfg["v_hi"]])
    return lo, hi


class KeeperController:
    def __init__(self, max_speed=60, kp=0.25, deadband_px=25, lookahead=4,
                 lost_hold=15, min_area=80,
                 min_radius=6, max_radius=80, min_circularity=0.6):
        self.max_speed = max_speed
        self.kp = kp
        self.deadband_px = deadband_px
        self.lost_hold = lost_hold
        self.min_area = min_area
        self.min_radius = min_radius            # ignore blobs smaller than the ball
        self.max_radius = max_radius            # ignore blobs bigger than the ball (boxes)
        self.min_circularity = min_circularity  # ignore non-round shapes (boxes)
        self.lo, self.hi = load_hsv()
        self.kf = BallKalman(lookahead=lookahead)
        self._missed = 0

    def _detect(self, hsv):
        mask = cv2.inRange(hsv, self.lo, self.hi)
        k = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        best_score = 0.0
        for c in cnts:
            area = cv2.contourArea(c)
            if area < self.min_area:
                continue
            (x, y), r = cv2.minEnclosingCircle(c)
            if r < self.min_radius or r > self.max_radius:
                continue                                # too small or too big (box)
            circularity = area / (np.pi * r * r) if r > 0 else 0.0
            if circularity < self.min_circularity:
                continue                                # not round (box/blob) -> reject
            score = circularity * area                  # prefer round AND solid
            if score > best_score:
                best_score = score
                best = (float(x), float(y), float(r))
        return best

    def process(self, frame):
        """Run one frame -> KeeperResult (found, motor cmd, and state for drawing)."""
        h, w = frame.shape[:2]
        center_x = w / 2.0
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        det = self._detect(hsv)

        self.kf.predict()
        radius = 0.0
        if det is not None:
            self.kf.correct(det[0], det[1])
            radius = det[2]
            self._missed = 0
        else:
            self._missed += 1
        e = self.kf.state()

        found = self.kf.initialized and self._missed <= self.lost_hold
        if found:
            error = e.pred_x - center_x
            if abs(error) < self.deadband_px:
                cmd = 0
            else:
                cmd = int(max(-self.max_speed, min(self.max_speed, self.kp * error)))
        else:
            error, cmd = 0.0, 0
        return KeeperResult(found, cmd, error, e.x, e.y, e.pred_x, radius, e.vx)

    def draw(self, frame, r: KeeperResult):
        """Annotate a frame for debugging (green=ball, blue=prediction, center line)."""
        h, w = frame.shape[:2]
        cv2.line(frame, (w // 2, 0), (w // 2, h), (80, 80, 80), 1)
        if r.found:
            cv2.circle(frame, (int(r.x), int(r.y)), 8, (0, 255, 0), 2)
            cv2.arrowedLine(frame, (int(r.x), int(r.y)), (int(r.pred_x), int(r.y)),
                            (255, 120, 0), 2, tipLength=0.3)
            txt = f"pred_x={r.pred_x:.0f} err={r.error:+.0f} cmd={r.cmd}"
            col = (0, 255, 0)
        else:
            txt = "ball lost -> hold"
            col = (0, 165, 255)
        cv2.putText(frame, txt, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        return frame