import math

from station.component_twin import ComponentTwinModel, angle_at
from station.config import load_exercise_config, match_exercise_key
from station.exercises import DECREASED, EXCESSIVE, WNL, ExerciseEvaluator, classify_arom
from station.pose import LANDMARKS, Point

CFG = load_exercise_config()


def leg_landmarks(side: str, hip_deg: float, knee_deg: float) -> dict[str, Point]:
    """Synthetic side-view landmarks: trunk to the left of the hip, leg to the right."""
    ids = LANDMARKS[side]
    hip = (500.0, 400.0)
    shoulder = (100.0, 400.0)
    a = math.radians(hip_deg)
    knee = (hip[0] + 200 * math.cos(a), hip[1] - 200 * math.sin(a))
    b = a + math.radians(knee_deg)  # shank bends further
    ankle = (knee[0] + 200 * math.cos(b), knee[1] - 200 * math.sin(b))
    foot = (ankle[0] + 40 * math.cos(b + math.pi / 2), ankle[1] - 40 * math.sin(b + math.pi / 2))
    pts = {"shoulder": shoulder, "hip": hip, "knee": knee, "ankle": ankle, "foot": foot, "heel": ankle}
    return {str(ids[k]): Point(x, y, 0.99) for k, (x, y) in pts.items()}


def run(exercise_key: str, profile, side="left", fps=30.0):
    """profile: list of (hip_deg, knee_deg) per frame. Returns evaluator."""
    twin = ComponentTwinModel(side, CFG["min_landmark_visibility"], CFG["filter"])
    ev = ExerciseEvaluator(exercise_key, CFG["exercises"][exercise_key], CFG)
    for i, (hip, knee) in enumerate(profile):
        t = i / fps
        landmarks = None if hip is None else leg_landmarks(side, hip, knee)
        ev.update(twin.update(landmarks, t), t)
    return ev


def rep(peak, frames=60, rest=20, knee=0.0, hold=10):
    up = [(peak * i / frames, knee) for i in range(frames)]
    top = [(peak, knee)] * hold
    down = [(peak * (frames - i) / frames, knee) for i in range(frames)]
    return [(0.0, 0.0)] * rest + up + top + down + [(0.0, 0.0)] * rest


def test_angle_at_right_angle():
    assert round(angle_at(Point(0, 1, 1), Point(0, 0, 1), Point(1, 0, 1))) == 90


def test_synthetic_landmarks_give_expected_joint_angles():
    twin = ComponentTwinModel("left", 0.5, CFG["filter"])
    joints = twin.update(leg_landmarks("left", 60, 30), 0.0)
    assert round(joints["hip"].angle) == 60
    assert round(joints["knee"].angle) == 30


def test_arom_classification_uses_reference_standard():
    assert classify_arom(78, (0, 80), 10) == WNL
    assert classify_arom(55, (0, 80), 10) == DECREASED
    assert classify_arom(95, (0, 80), 10) == EXCESSIVE


def test_straight_leg_raise_valid_repetitions():
    ev = run("straight_leg_raising", rep(78) + rep(80))
    assert ev.valid == 2
    assert ev.session_arom()[0] == WNL


def test_bent_knee_makes_repetition_invalid():
    ev = run("straight_leg_raising", rep(75, knee=30))
    assert ev.count("invalid") == 1
    assert ev.deviation_counts.get("knee_bent") == 1


def test_small_lift_is_incomplete():
    ev = run("straight_leg_raising", rep(30))
    assert ev.count("incomplete") == 1


def test_tracking_loss_prevents_valid_count_and_prompts_positioning():
    profile = rep(78)
    profile[90:130] = [(None, None)] * 40  # ~1.3 s lost at the top
    ev = run("straight_leg_raising", profile)
    assert ev.valid == 0
    assert ev.count("incomplete") == 1


def test_prone_leg_flexion_uses_knee_as_primary_joint():
    profile = [(0.0, k) for k in [0.0] * 20 + list(range(0, 130, 2)) + [130] * 10 + list(range(130, 0, -2)) + [0.0] * 20]
    ev = run("prone_leg_flexion", profile)
    assert ev.valid == 1
    assert ev.session_arom()[0] == WNL


def test_side_leg_lift_decreased_rom():
    ev = run("side_leg_lifts", rep(30), side="right")
    assert ev.valid == 1
    assert ev.session_arom()[0] == DECREASED


def test_backend_exercise_names_map_to_station_keys():
    assert match_exercise_key("Straight Leg Raising") == "straight_leg_raising"
    assert match_exercise_key("Side Leg Lifts") == "side_leg_lifts"
    assert match_exercise_key("Prone Leg Flexion") == "prone_leg_flexion"
    assert match_exercise_key("Seated Knee Extension") is None
