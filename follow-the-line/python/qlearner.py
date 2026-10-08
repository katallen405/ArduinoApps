"""
Tabular Q-learning for line-following.

State: which calibrated bin the color-sensor reading falls into.
Action: a discrete (left_speed, right_speed) motor command.
Reward: how centered the line position is -- this is what lets the
agent discover "sprint when centered, brake when off to either side"
by trial and reward, instead of being handed target speeds directly.

Pure Python, no numpy -- matches the rest of this LEGO codebase.
"""

import random

ACTIONS = [
    (90, 90),   # 0 SPRINT
    (40, 85),   # 1 SOFT_LEFT
    (10, 90),   # 2 HARD_LEFT
    (85, 40),   # 3 SOFT_RIGHT
    (90, 10),   # 4 HARD_RIGHT
]

N_BINS = 7


class Calibrator:
    DECAY = 0.05

    def __init__(self):
        self.lo, self.hi = 50.0, 50.0

    def update(self, r):
        self.lo = min(self.lo, r)
        self.hi = max(self.hi, r)
        self.lo += self.DECAY
        self.hi -= self.DECAY

    def mid(self):
        return 0.5 * (self.lo + self.hi)

    def normalized(self, r):
        span = max(self.hi - self.lo, 1e-6)
        x = (r - self.mid()) / (0.5 * span)
        return max(-1.0, min(1.0, x))


def bin_of(x):
    idx = int((x + 1.0) / 2.0 * N_BINS)
    return max(0, min(N_BINS - 1, idx))


class QLearner:
    def __init__(self, alpha=0.3, gamma=0.7, epsilon=0.3,
                 epsilon_min=0.05, epsilon_decay=0.9995, warm_start=True):
        self.alpha, self.gamma = alpha, gamma
        self.epsilon, self.epsilon_min, self.epsilon_decay = epsilon, epsilon_min, epsilon_decay
        self.q = {}
        self.prev_state = None
        self.prev_action = None
        if warm_start:
            self._seed()

    def _seed(self):
        """Give off-center bins a head start toward turning instead of
        relying on the all-zero Q-table's tie-break, which always
        defaults to action 0 (SPRINT). If it turns the wrong way at
        corners, swap the action indices below (1/2 <-> 3/4)."""
        center = N_BINS // 2
        for s in range(N_BINS):
            offset = s - center
            if offset == 0:
                continue
            action = (2 if offset <= -2 else 1) if offset < 0 else (4 if offset >= 2 else 3)
            self.q[(s, action)] = 0.5

    def _q(self, state, action):
        return self.q.get((state, action), 0.0)

    def _best_action(self, state):
        return max(range(len(ACTIONS)), key=lambda a: self._q(state, a))

    def select_action(self, state):
        if random.random() < self.epsilon:
            action = random.randrange(len(ACTIONS))
        else:
            action = self._best_action(state)
        self.prev_state, self.prev_action = state, action
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        return action

    def observe(self, x, new_state):
        if self.prev_state is None:
            return None
        reward = 1.0 - abs(x)
        best_next = self._q(new_state, self._best_action(new_state))
        old = self._q(self.prev_state, self.prev_action)
        self.q[(self.prev_state, self.prev_action)] = old + self.alpha * (
            reward + self.gamma * best_next - old
        )
        return reward

    def reset_transition(self):
        self.prev_state = None
        self.prev_action = None

    def policy_summary(self):
        lines = []
        for s in range(N_BINS):
            a = self._best_action(s)
            lines.append("bin {}: best={} (q={:.2f})".format(s, ACTIONS[a], self._q(s, a)))
        return "\n".join(lines)