"""
kalman.py — 2D constant-velocity Kalman filter for tracking (my contribution).

Turns noisy per-frame ball detections into a smoothed position, an estimated
velocity, and a short-horizon prediction. Two-step predict/correct cycle per frame.
If a frame has no detection, call predict() and skip correct() — it coasts on the
motion model (dropout handling).

    from kalman import BallKalman
    kf = BallKalman(lookahead=4)
    kf.predict()
    if detected: kf.correct(cx, cy)
    est = kf.state()   # est.x, est.y, est.vx, est.vy, est.pred_x, est.pred_y

process_var     : trust in the motion model (larger => snappier, jumpier)
measurement_var : trust in the detector (larger => smoother, laggier)
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class KalmanEstimate:
    x: float
    y: float
    vx: float
    vy: float
    pred_x: float
    pred_y: float


class BallKalman:
    def __init__(self, lookahead=4, dt=1.0, process_var=1e-2, measurement_var=5e-1):
        self.lookahead = lookahead
        self.dt = dt
        self._initialized = False
        self.x = np.zeros((4, 1))
        self.F = np.array([[1, 0, dt, 0],
                           [0, 1, 0, dt],
                           [0, 0, 1,  0],
                           [0, 0, 0,  1]], dtype=float)
        self.H = np.array([[1, 0, 0, 0],
                           [0, 1, 0, 0]], dtype=float)
        self.P = np.eye(4) * 1000.0
        self.Q = np.eye(4) * process_var
        self.R = np.eye(2) * measurement_var
        self.I = np.eye(4)

    def predict(self):
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x[0, 0], self.x[1, 0]

    def correct(self, cx, cy):
        z = np.array([[cx], [cy]], dtype=float)
        if not self._initialized:
            self.x[0, 0], self.x[1, 0] = cx, cy
            self._initialized = True
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (self.I - K @ self.H) @ self.P
        return self.x[0, 0], self.x[1, 0]

    def state(self):
        px, py, vx, vy = self.x[:, 0]
        return KalmanEstimate(px, py, vx, vy,
                              px + vx * self.lookahead,
                              py + vy * self.lookahead)

    @property
    def initialized(self):
        return self._initialized


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    kf = BallKalman(lookahead=3)
    print("frame | true(x)  meas(x)  filt(x)  vx   pred(x)  note")
    for t in range(20):
        true_x = 100 + 20 * t
        drop = 8 <= t <= 10
        kf.predict()
        if not drop:
            mx = true_x + rng.normal(0, 8)
            kf.correct(mx, 200 + rng.normal(0, 8))
            m, note = f"{mx:7.1f}", ""
        else:
            m, note = "   ----", "DROPOUT (coasting)"
        s = kf.state()
        print(f"{t:5d} | {true_x:7.0f} {m} {s.x:8.1f} {s.vx:4.1f} {s.pred_x:8.1f}  {note}")
