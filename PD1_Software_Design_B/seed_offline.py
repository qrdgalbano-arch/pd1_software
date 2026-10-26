from station.config import get_settings
from station.storage import LocalStore

store = LocalStore(get_settings().database_path)
store.cache_patients([{"id": 1, "full_name": "Demo Patient", "is_active": True}])
rows = [(1, "Straight Leg Raising", "straight_leg_raising"),
        (2, "Ankle Pump", "ankle_pump"),
        (3, "Prone Leg Flexion", "prone_leg_flexion")]
store.cache_prescriptions(1, [{
    "id": i, "patient_id": 1, "exercise": {"name": n}, "exercise_key": k,
    "repetitions_target": 10, "duration_limit_seconds": 180, "is_active": True,
} for i, n, k in rows])
print("Offline demo patient and 3 prescriptions ready")