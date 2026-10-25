import json
from station.config import get_settings
from station.sync import BackendClient

def positive_integer(label, maximum):
    value = int(input(label).strip())
    if not 1 <= value <= maximum:
        raise ValueError(f"Enter a value between 1 and {maximum}.")
    return value

def main():
    client = BackendClient(get_settings())

    response = client.request("GET", "/staff/patients")
    response.raise_for_status()
    patients = [
        p for p in response.json()
        if p.get("is_active", True)
    ]
    if not patients:
        raise SystemExit("No active patients found. No changes made.")

    print("\nAvailable patients:")
    for patient in patients:
        print(f"  ID {patient['id']}: {patient.get('full_name', '')}")

    patient_id = int(input("\nPatient ID to receive ankle pumps: ").strip())
    selected = next(
        (p for p in patients if p["id"] == patient_id), None
    )
    if selected is None:
        raise SystemExit("Patient ID not in the active patient list.")

    response = client.request(
        "GET", f"/staff/patients/{patient_id}/prescriptions"
    )
    response.raise_for_status()
    existing = response.json()

    names = {"ankle pump", "ankle pumps", "ankle pumping"}
    for item in existing:
        name = item.get("exercise", {}).get("name", "").strip().lower()
        if item.get("is_active") and name in names:
            print(
                f"\nActive ankle-pump prescription already exists: "
                f"ID {item['id']}."
            )
            print("Reload patients in the station and reselect this patient.")
            return

    print("\nEnter PT-provided values or your intentional DEMO settings.")
    reps = positive_integer("Repetitions target: ", 1000)
    duration = positive_integer("Session duration limit, seconds: ", 86400)
    schedule = input(
        "Scheduled days, using your backend's usual format: "
    ).strip()
    if not 3 <= len(schedule) <= 100:
        raise SystemExit("Scheduled-days text must contain 3–100 characters.")

    response = client.request("GET", "/staff/exercises")
    response.raise_for_status()
    exercise = next(
        (
            e for e in response.json()
            if e.get("name", "").strip().lower() in names
        ),
        None,
    )

    catalogue = {
        "name": "Ankle Pump",
        "description": (
            "Lying ankle dorsiflexion and plantarflexion. "
            "Directional population references are +20 degrees and "
            "-50 degrees, respectively; these are not prescribed targets."
        ),
        "default_repetitions": reps,
        "default_duration_seconds": duration,
    }
    prescription = {
        "patient_id": patient_id,
        "exercise_id": exercise["id"] if exercise else None,
        "repetitions_target": reps,
        "duration_limit_seconds": duration,
        "scheduled_days": schedule,
    }

    print("\nReview before saving:")
    print(f"Patient: {selected.get('full_name', '')} (ID {patient_id})")
    if exercise is None:
        print("A new exercise catalogue entry will also be created:")
        print(json.dumps(catalogue, indent=2))
    print("Prescription:")
    print(json.dumps(prescription, indent=2))
    print("No existing prescriptions will be changed or deleted.")

    if input("\nType SAVE to create these records: ").strip() != "SAVE":
        print("Cancelled. No changes made.")
        return

    if exercise is None:
        response = client.request("POST", "/staff/exercises", json=catalogue)
        response.raise_for_status()
        exercise = response.json()
        prescription["exercise_id"] = exercise["id"]

    response = client.request(
        "POST", "/staff/prescriptions", json=prescription
    )
    response.raise_for_status()
    created = response.json()

    print(f"\nAnkle-pump prescription created: ID {created['id']}")
    print("Reload patients in the station, then reselect this patient.")
    print("The same prescription is available to Designs A, B, and C.")
    print("Clinical approval flags and joint-angle tolerances were not changed.")

if __name__ == "__main__":
    main()
