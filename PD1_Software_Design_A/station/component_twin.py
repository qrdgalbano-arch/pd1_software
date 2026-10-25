"""Design 1 - Component Twin-based Platform.

Each lower-extremity joint (hip, knee, ankle) is a separate, independently
updated component twin. Every component owns its own landmarks, smoothing
filter, patient-specific baseline, angle, angular velocity, ROM history,
and position-hold time. Components never read each other's state; the
exercise evaluator combines them only at evaluation time.
"""

import math
from dataclasses import dataclass, field

from station.filters import OneEuroFilter
from station.pose import LANDMARKS, Point


def angle_at(a: Point, b: Point, c: Point) -> float:
    """Interior angle ABC; coordinates must share one unit system."""
    v1 = (a.x - b.x, a.y - b.y, a.z - b.z)
    v2 = (c.x - b.x, c.y - b.y, c.z - b.z)

    if not all(math.isfinite(v) for v in (*v1, *v2)):
        return float("nan")

    n1 = math.sqrt(sum(v * v for v in v1))
    n2 = math.sqrt(sum(v * v for v in v2))

    if n1 < 1e-6 or n2 < 1e-6:
        return float("nan")

    cosine = sum(x * y for x, y in zip(v1, v2)) / (n1 * n2)
    cosine = max(-1.0, min(1.0, cosine))

    return math.degrees(math.acos(cosine))


# Joint definitions: (landmark names forming the angle, conversion to clinical angle)
JOINT_DEFINITIONS = {
    # 0 deg = thigh in line with trunk; flexion / abduction / extension
    "hip": (("shoulder", "hip", "knee"), lambda inner: 180.0 - inner),
    # 0 deg = knee straight; positive = flexion
    "knee": (("hip", "knee", "ankle"), lambda inner: 180.0 - inner),
    # 0 deg = neutral ankle; positive = dorsiflexion, negative = plantarflexion
    "ankle": (("knee", "ankle", "foot"), lambda inner: 90.0 - inner),
}


@dataclass
class JointState:
    name: str
    side: str
    tracked: bool = False
    angle: float | None = None
    raw_angle: float | None = None
    velocity_dps: float = 0.0
    baseline: float = 0.0
    rom_min: float | None = None
    rom_max: float | None = None
    hold_seconds: float = 0.0
    lost_seconds: float = 0.0
    opposite_raised: bool = False

    def as_dict(self) -> dict:
        def r(value):
            return None if value is None else round(value, 1)

        return {
            "name": self.name,
            "side": self.side,
            "tracked": self.tracked,
            "angle": r(self.angle),
            "velocity_dps": round(self.velocity_dps, 1),
            "baseline": round(self.baseline, 1),
            "rom_min": r(self.rom_min),
            "rom_max": r(self.rom_max),
            "hold_seconds": round(self.hold_seconds, 2),
            "lost_seconds": round(self.lost_seconds, 2),
        }


class JointComponentTwin:
    """Independent twin of one joint."""

    HOLD_BAND_DEG = 5.0
    HOLD_MAX_SPEED_DPS = 20.0
    POINT_FILTER = {"min_cutoff": 0.6, "beta": 0.01, "d_cutoff": 1.0}
    MAX_JUMP_DPS = 360.0
    MAX_REJECTS = 5

    def __init__(self, name: str, side: str, min_visibility: float, filter_cfg: dict):
        self.name = name
        self.side = side
        self.min_visibility = min_visibility
        names, self._convert = JOINT_DEFINITIONS[name]
        self._indices = [str(LANDMARKS[side][n]) for n in names]
        self._filter = OneEuroFilter(**filter_cfg)
        self._pt_filters = [
            tuple(OneEuroFilter(**self.POINT_FILTER) for _ in range(3))
            for _ in self._indices
            ]
        self._rejects = 0
        self.state = JointState(name=name, side=side)
        self._last_t: float | None = None
        self._lost_since: float | None = None
        self._calibration: list[float] = []

    # --- patient-specific calibration -------------------------------------
    def reset_tracking(self) -> None:
        self._filter.reset()
        for filters in self._pt_filters:
            for point_filter in filters:
                point_filter.reset()
        self.state.raw_angle = None
        self._rejects = 0
    
    def start_calibration(self) -> None:
        self._calibration = []

    def finish_calibration(self, max_offset: float) -> None:
        if self._calibration:
            values = sorted(self._calibration)
            median = values[len(values) // 2]
            self.state.baseline = max(-max_offset, min(max_offset, median))
        self._calibration = []

    def reset_session(self) -> None:
        self.state.rom_min = None
        self.state.rom_max = None
        self.state.hold_seconds = 0.0

    # --- per-frame update ---------------------------------------------------
    def update(self, landmarks: dict[str, Point] | None, t: float, calibrating: bool) -> JointState:
        dt = 0.0 if self._last_t is None else max(0.0, t - self._last_t)
        self._last_t = t
        s = self.state

        points = None
        if landmarks is not None:
            points = [landmarks.get(i) for i in self._indices]
            if any(
                p is None
                or not all(
                    math.isfinite(v)
                    for v in (p.x, p.y, p.z, p.visibility)
                )
                or p.visibility < self.min_visibility
                for p in points
            ):
                points = None

        raw = float("nan")
        if points is not None:
            points = [
                Point(
                    x=fx(p.x, t),
                    y=fy(p.y, t),
                    z=fz(p.z, t),
                    visibility=p.visibility,
                )
                for p, (fx, fy, fz) in zip(points, self._pt_filters)
            ]
            raw = self._convert(angle_at(*points))

        if points is None or math.isnan(raw):
            s.tracked = False
            if self._lost_since is None:
                self._lost_since = t
            s.lost_seconds = t - self._lost_since
            s.velocity_dps = 0.0
            if s.lost_seconds > 0.5:
                self.reset_tracking()
            return s

        if (
            s.raw_angle is not None and dt > 0
            and abs(raw - s.raw_angle) / dt > self.MAX_JUMP_DPS
            and self._rejects < self.MAX_REJECTS
        ):
            self._rejects += 1
            return s
        self._rejects = 0
        self._lost_since = None
        s.lost_seconds = 0.0
        s.tracked = True
        s.raw_angle = raw

        if calibrating:
            self._calibration.append(raw)

        # Check if opposite leg is lifting instead of this target leg
        s.opposite_raised = False
        if landmarks is not None and self.name == "hip":
            opp_side = "right" if self.side == "left" else "left"
            names, _ = JOINT_DEFINITIONS[self.name]
            opp_pts = [landmarks.get(str(LANDMARKS[opp_side][n])) for n in names]
            if opp_pts and not any(p is None or p.visibility < self.min_visibility for p in opp_pts):
                raw_opp = self._convert(angle_at(*opp_pts))
                # Opposite leg is lifting (> 20 deg) while prescribed leg remains flat (< 15 deg)
                if raw_opp > 20.0 and raw < 15.0:
                    s.opposite_raised = True

        previous = s.angle
        self._med = (getattr(self, "_med", []) + [raw])[-5:]
        raw_m = sorted(self._med)[len(self._med) // 2]
        s.angle = self._filter(raw_m - s.baseline, t)
        s.velocity_dps = self._filter.derivative

        if not calibrating:
            s.rom_min = s.angle if s.rom_min is None else min(s.rom_min, s.angle)
            s.rom_max = s.angle if s.rom_max is None else max(s.rom_max, s.angle)
            if (
                previous is not None
                and abs(s.velocity_dps) < self.HOLD_MAX_SPEED_DPS
                and s.rom_max is not None
                and s.angle >= s.rom_max - self.HOLD_BAND_DEG
            ):
                s.hold_seconds += dt
        return s


@dataclass
class ComponentTwinModel:
    """Container of the three independent joint twins for the affected side."""

    side: str
    min_visibility: float
    filter_cfg: dict
    joints: dict[str, JointComponentTwin] = field(default_factory=dict)
    active_side: str = "left"

    def __post_init__(self) -> None:
        self.active_side = self.side
        self.joints = {
            name: JointComponentTwin(name, self.side, self.min_visibility, self.filter_cfg)
            for name in ("hip", "knee", "ankle")
        }

    def _resolve_active_side(self, landmarks):
        """Camera proximity never changes the prescribed anatomical side."""
        return self.side

    def update(self, landmarks: dict[str, Point] | None, t: float, calibrating: bool = False) -> dict[str, JointState]:
        if not calibrating:
            self.active_side = self._resolve_active_side(landmarks)

        self.active_side = self.side

        # Update joint indices to follow the prescribed anatomical side
        for twin in self.joints.values():
            names, _ = JOINT_DEFINITIONS[twin.name]
            twin._indices = [str(LANDMARKS[self.active_side][n]) for n in names]

        return {name: twin.update(landmarks, t, calibrating) for name, twin in self.joints.items()}

    def start_calibration(self) -> None:
        for twin in self.joints.values():
            twin.start_calibration()

    def finish_calibration(self, max_offset: float) -> None:
        for twin in self.joints.values():
            twin.finish_calibration(max_offset)
            twin.reset_session()

    def as_dict(self) -> dict:
        return {name: twin.state.as_dict() for name, twin in self.joints.items()}

    def reset_tracking(self) -> None:
        for twin in self.joints.values():
            twin.reset_tracking()

# POSE3D_BACKEND_PATCH_V1

# POSE_ORIENTATION_PATCH_V1
