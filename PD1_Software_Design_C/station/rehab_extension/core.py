
"""Shared assessment and visual feedback; independent of avatar scope."""
import math

WNL = "Within Normal Limits"
DECREASED = "Decreased Range of Motion"
UNAVAILABLE = "Assessment unavailable"

def finite(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )

def assess_arom(peak, reference, wnl_tolerance=None, tracked=True):
    """Peak/reference are directional magnitudes, not signed ankle angles."""
    provisional = wnl_tolerance is None
    result = {
        "label": UNAVAILABLE,
        "provisional": provisional,
        "tag": "Provisional – PT criteria not set" if provisional else None,
        "note": None,
        "peak_deg": peak if finite(peak) else None,
        "reference_deg": reference if finite(reference) else None,
    }
    if not tracked or not finite(peak) or not finite(reference):
        return result
    if peak < 0 or reference < 0:
        return result
    tolerance = 0 if provisional else wnl_tolerance
    if not finite(tolerance) or tolerance < 0:
        return result
    result["label"] = DECREASED if peak < reference - tolerance else WNL
    if peak > reference:
        result["note"] = "exceeds reference"
    return result

def position(angle, target, tolerance, tracked=True, approved=False):
    if not tracked or not finite(angle):
        return {"label": "Tracking uncertain", "deviation_deg": None}
    if (
        not approved
        or not finite(target)
        or not finite(tolerance)
        or tolerance < 0
    ):
        return {"label": "PT criteria not set", "deviation_deg": None}
    deviation = angle - target
    return {
        "label": (
            "Within prescribed limits"
            if abs(deviation) <= tolerance
            else "Outside prescribed limits"
        ),
        "deviation_deg": deviation,
    }

def redness(
    deviation, tolerance, full_scale, *,
    tracked=True, approved=False,
    moving=False, inside_prescribed_range=False,
):
    if not tracked or not approved:
        return 0.0
    if moving and inside_prescribed_range:
        return 0.0
    if not all(finite(v) for v in (deviation, tolerance, full_scale)):
        return 0.0
    if tolerance < 0 or full_scale <= 0:
        return 0.0
    return max(0.0, min(1.0, (abs(deviation) - tolerance) / full_scale))

def joint_redness(scope, parameters):
    """Rendering scope never changes evaluation of the three joints."""
    if scope not in ("component", "leg", "whole_body"):
        raise ValueError("Unknown design_scope")
    return {
        name: redness(**parameters[name]) if name in parameters else 0.0
        for name in ("hip", "knee", "ankle")
    }

def target_completion(peak, target, tolerance, *, endpoint=False, approved=False):
    if not endpoint:
        return None
    if not approved or not all(finite(v) for v in (peak, target, tolerance)):
        return None
    if tolerance < 0:
        return None
    return "Target reached" if peak >= target - tolerance else "Target not reached"

def compare_sessions(current_peaks, previous_peaks=None):
    current = [v for v in current_peaks if finite(v)]
    previous = [
        v for v in (previous_peaks or []) if finite(v)
    ]
    average = sum(current) / len(current) if current else None
    prior_average = sum(previous) / len(previous) if previous else None
    return {
        "avg_peak_arom": average,
        "max_peak": max(current) if current else None,
        "previous_avg_peak_arom": prior_average,
        "previous_max_peak": max(previous) if previous else None,
        "difference_deg": (
            average - prior_average
            if average is not None and prior_average is not None
            else None
        ),
        "history_status": (
            "Previous session available" if previous else "No previous session"
        ),
    }
