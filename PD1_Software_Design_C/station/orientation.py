"""Experimental inferred-3D orientation packets; not measured depth."""
import math


class OrientationTracker:
    def __init__(self, minimum=0.7):
        self.minimum = minimum
        self.reset()

    def reset(self):
        self.candidate = None
        self.since = None
        self.last = None
        self.previous_session = None

    def update(self, points, t):
        if self.last is not None and t - self.last > 0.5:
            self.candidate = self.since = None
        self.last = t

        result = {
            "available": False,
            "orientation_valid": False,
            "landmarks": {},
            "near_side": None,
            "reason": "No usable inferred world landmarks",
            "units": "m",
            "depth_kind": "monocular_inferred",
        }

        if not points:
            self.candidate = self.since = None
            return result

        for key, p in points.items():
            values = (p.x, p.y, p.z, p.visibility)
            if (
                all(math.isfinite(v) for v in values)
                and p.visibility >= self.minimum
            ):
                result["landmarks"][str(key)] = {
                    "x": p.x, "y": p.y, "z": p.z,
                    "visibility": p.visibility,
                }

        visible = result["landmarks"]
        result["available"] = bool(visible)

        if not all(str(i) in visible for i in (11, 12, 23, 24)):
            self.candidate = self.since = None
            result["reason"] = "Keep both shoulders and hips visible"
            return result

        def xyz(i):
            p = visible[str(i)]
            return [p["x"], p["y"], p["z"]]

        def sub(a, b):
            return [x-y for x, y in zip(a, b)]

        def dot(a, b):
            return sum(x*y for x, y in zip(a, b))

        def unit(v):
            length = math.sqrt(dot(v, v))
            return None if length < 1e-5 else [x/length for x in v]

        ls, rs, lh, rh = [xyz(i) for i in (11, 12, 23, 24)]
        hips = [(a+b)/2 for a, b in zip(lh, rh)]
        shoulders = [(a+b)/2 for a, b in zip(ls, rs)]

        left = unit(sub(lh, rh))
        up = sub(shoulders, hips)

        if left is not None:
            projection = dot(up, left)
            up = unit([v-projection*x for v, x in zip(up, left)])

        if left is None or up is None:
            self.candidate = self.since = None
            result["reason"] = "Ambiguous torso orientation"
            return result

        result["orientation_valid"] = True
        result["basis"] = {"left": left, "up": up}
        result["reason"] = None

        # Engineering heuristics, not clinically validated thresholds.
        hip_difference = lh[2] - rh[2]
        shoulder_difference = ls[2] - rs[2]
        margin = 0.04

        candidate = None
        if hip_difference < -margin and shoulder_difference < -margin:
            candidate = "left"
        elif hip_difference > margin and shoulder_difference > margin:
            candidate = "right"

        if candidate is None:
            self.candidate = self.since = None
        elif candidate != self.candidate:
            self.candidate, self.since = candidate, t
        elif t - self.since >= 0.6:
            result["near_side"] = candidate

        return result

# POSE_ORIENTATION_PATCH_V1
