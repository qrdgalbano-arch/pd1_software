"""Rule-based exercise evaluation on top of the Component Twin model.

- Repetition state machine on the exercise's primary joint twin.
- Observable deviations checked on the other joint twins.
- AROM classification against the reference ROM standard:
    Straight leg raising 0-80 deg, Side leg lifts 0-45 deg, Prone leg flexion 0-135 deg.
- Optional per-exercise "primary_sign" (default 1) multiplies the primary joint angle,
  so a negative angle such as ankle plantarflexion can drive the repetition state machine.
"""

import statistics
from dataclasses import dataclass, field

from station.component_twin import JointState

WNL = "Within Normal Limits"
DECREASED = "Decreased Range of Motion"
EXCESSIVE = "Excessive Range of Motion"
UNAVAILABLE = "Tracking unavailable"


def classify_arom(peak: float | None, rom_standard: tuple[float, float], tolerance: float) -> str:
    if peak is None:
        return UNAVAILABLE
    upper = rom_standard[1]
    if peak < upper - tolerance:
        return DECREASED
    if peak > upper + tolerance:
        return EXCESSIVE
    return WNL


@dataclass
class Repetition:
    number: int
    started_at: float
    ended_at: float = 0.0
    peak_deg: float = 0.0
    hold_seconds: float = 0.0
    deviations: set[str] = field(default_factory=set)
    tracking_lost: bool = False
    too_fast: bool = False
    result: str = ""  # valid | invalid | incomplete
    arom: str = ""

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "duration_s": round(self.ended_at - self.started_at, 2),
            "peak_deg": round(self.peak_deg, 1),
            "hold_seconds": round(self.hold_seconds, 2),
            "deviations": sorted(self.deviations),
            "tracking_lost": self.tracking_lost,
            "too_fast": self.too_fast,
            "result": self.result,
            "arom": self.arom,
        }


@dataclass
class Prompt:
    id: str
    text: str
    level: str  # info | warning | error | success
    seq: int


class ExerciseEvaluator:
    def __init__(self, exercise_key: str, exercise_cfg: dict, global_cfg: dict):
        self.key = exercise_key
        self.cfg = exercise_cfg
        self.primary = exercise_cfg["primary_joint"]
        self.sign = float(exercise_cfg.get("primary_sign", 1))
        self.rom_standard = tuple(exercise_cfg["rom_standard_deg"])
        self.tolerance = float(global_cfg.get("rom_tolerance_deg", 10))
        self.loss_prompt_s = float(global_cfg.get("tracking_loss_prompt_seconds", 1.0))
        self.confirm_s = float(global_cfg.get("deviation_confirm_seconds", 0.25))
        self.messages = {d["id"]: d["message"] for d in exercise_cfg.get("deviations", [])}
        self.messages["too_fast"] = "Move more slowly."

        self.reps: list[Repetition] = []
        self.current: Repetition | None = None
        self.prompt: Prompt | None = None
        self._seq = 0
        self._deviation_since: dict[str, float] = {}
        self._active_deviations: set[str] = set()
        self.deviation_counts: dict[str, int] = {}
        self.feedback_latencies: list[float] = []
        self._last_t: float | None = None

    # --- prompts ------------------------------------------------------------
    def _say(self, prompt_id: str, text: str, level: str) -> None:
        if self.prompt and self.prompt.id == prompt_id and self.prompt.text == text:
            return
        self._seq += 1
        self.prompt = Prompt(prompt_id, text, level, self._seq)

    # --- counters -----------------------------------------------------------
    def count(self, result: str) -> int:
        return sum(1 for rep in self.reps if rep.result == result)

    @property
    def valid(self) -> int:
        return self.count("valid")

    @property
    def peaks(self) -> list[float]:
        return [rep.peak_deg for rep in self.reps if rep.result != "incomplete"]

    def session_arom(self) -> tuple[str, float | None]:
        peaks = self.peaks or [rep.peak_deg for rep in self.reps]
        if not peaks:
            return UNAVAILABLE, None
        peak = statistics.median(peaks)
        return classify_arom(peak, self.rom_standard, self.tolerance), round(peak, 1)

    # --- per-frame update ---------------------------------------------------
    def _tracking_ok(self, joints: dict[str, JointState]) -> tuple[bool, float]:
        required = self.cfg.get("required_joints", [self.primary])
        lost = [joints[j].lost_seconds for j in required if not joints[j].tracked]
        return (not lost), (max(lost) if lost else 0.0)

    def _check_deviations(self, joints: dict[str, JointState], t: float) -> set[str]:
        found: set[str] = set()
        for rule in self.cfg.get("deviations", []):
            if rule["id"] == "wrong_leg_raised":
                if joints.get("hip") and joints["hip"].opposite_raised:
                    found.add("wrong_leg_raised")
                continue

            joint = joints[rule["joint"]]
            if not joint.tracked or joint.angle is None:
                continue
            value = joint.angle
            hit = value > rule["value"] if rule["op"] == ">" else value < rule["value"]
            if hit:
                found.add(rule["id"])

        primary = joints[self.primary]
        if primary.tracked and abs(primary.velocity_dps) > self.cfg.get("max_speed_dps", 9999):
            found.add("too_fast")

        confirmed: set[str] = set()
        for dev in found:
            since = self._deviation_since.setdefault(dev, t)
            if t - since >= self.confirm_s:
                confirmed.add(dev)
        for dev in list(self._deviation_since):
            if dev not in found:
                del self._deviation_since[dev]
        return confirmed

    def update(self, joints: dict[str, JointState], t: float) -> Repetition | None:
        """Process one frame. Returns a Repetition when one has just finished."""
        dt = 0.0 if self._last_t is None else max(0.0, t - self._last_t)
        self._last_t = t
        tracking_ok, lost_s = self._tracking_ok(joints)
        primary = joints[self.primary]

        if not tracking_ok:
            if self.current is not None:
                self.current.tracking_lost = True
            if lost_s >= self.loss_prompt_s:
                side = primary.side
                self._say(
                    "positioning",
                    f"Move into the camera view so your {side} hip, knee, and ankle are visible.",
                    "warning",
                )
            return None

        if self.prompt and self.prompt.id == "positioning":
            self._say("tracking_ok", "Tracking restored. Continue the exercise.", "info")

        angle = (primary.angle or 0.0) * self.sign
        confirmed = self._check_deviations(joints, t)
        for dev in confirmed - self._active_deviations:
            self.deviation_counts[dev] = self.deviation_counts.get(dev, 0) + 1
            self.feedback_latencies.append(self.confirm_s)
            self._say(dev, self.messages.get(dev, dev), "error")
        self._active_deviations = confirmed

        finished: Repetition | None = None

        if self.current is None:
            if angle > self.cfg["rep_start_deg"]:
                self.current = Repetition(number=len(self.reps) + 1, started_at=t)
        if self.current is not None:
            rep = self.current
            rep.peak_deg = max(rep.peak_deg, angle)
            if angle >= rep.peak_deg - 5.0 and abs(primary.velocity_dps) < 20.0:
                rep.hold_seconds += dt
            for dev in confirmed:
                if dev == "too_fast":
                    rep.too_fast = True
                else:
                    rep.deviations.add(dev)

            upper = self.rom_standard[1]
            if angle > upper + self.tolerance:
                self._say("over_range", "Lower slightly - you are beyond the target range.", "warning")

            if angle < self.cfg["rest_max_deg"]:
                rep.ended_at = t
                rep.arom = classify_arom(rep.peak_deg, self.rom_standard, self.tolerance)
                if rep.tracking_lost or rep.peak_deg < self.cfg["incomplete_below_deg"]:
                    rep.result = "incomplete"
                    self._say("rep_incomplete", f"Repetition {rep.number} incomplete - lift through the full range.", "warning")
                elif rep.deviations or rep.too_fast:
                    rep.result = "invalid"
                    self._say("rep_invalid", f"Repetition {rep.number} not counted - check your form.", "warning")
                else:
                    rep.result = "valid"
                    self._say("rep_valid", f"Good. {self.valid + 1} valid repetitions.", "success")
                self.reps.append(rep)
                self.current = None
                finished = rep
        return finished

    def error_summary(self) -> str:
        parts = [f"{self.messages.get(k, k)} x{v}" for k, v in sorted(self.deviation_counts.items())]
        return "; ".join(parts)

    def snapshot(self) -> dict:
        arom, peak = self.session_arom()
        live_peak = self.current.peak_deg if self.current else None
        return {
            "valid": self.valid,
            "invalid": self.count("invalid"),
            "incomplete": self.count("incomplete"),
            "in_repetition": self.current is not None,
            "live_peak_deg": None if live_peak is None else round(live_peak, 1),
            "live_arom": None if live_peak is None else classify_arom(live_peak, self.rom_standard, self.tolerance),
            "session_arom": arom,
            "session_peak_deg": peak,
            "active_deviations": sorted(self._active_deviations),
            "repetitions": [rep.as_dict() for rep in self.reps[-10:]],
            "prompt": None if self.prompt is None else self.prompt.__dict__,
        }
