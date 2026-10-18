def test_staff_lists_only_active_exercises(
    client,
    seeded_data,
    staff_headers,
):
    response = client.get("/staff/exercises", headers=staff_headers)

    assert response.status_code == 200

    exercises = response.json()
    assert [exercise["name"] for exercise in exercises] == [
        "Seated Knee Extension",
    ]
    assert exercises[0]["is_active"] is True


def test_staff_creates_an_exercise(client, seeded_data, staff_headers):
    response = client.post(
        "/staff/exercises",
        headers=staff_headers,
        json={
            "name": "Supported Sit to Stand",
            "description": "Stand up slowly using chair support.",
            "default_repetitions": 8,
            "default_duration_seconds": 75,
        },
    )

    assert response.status_code == 201
    exercise = response.json()
    assert exercise["id"] > 0
    assert exercise["name"] == "Supported Sit to Stand"
    assert exercise["description"] == (
        "Stand up slowly using chair support."
    )
    assert exercise["default_repetitions"] == 8
    assert exercise["default_duration_seconds"] == 75
    assert exercise["is_active"] is True


def test_staff_cannot_create_duplicate_exercise(
    client,
    seeded_data,
    staff_headers,
):
    response = client.post(
        "/staff/exercises",
        headers=staff_headers,
        json={
            "name": "Seated Knee Extension",
            "description": "Duplicate record.",
            "default_repetitions": 10,
            "default_duration_seconds": 90,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Exercise name already exists"


def test_staff_creates_prescription_for_patient(
    client,
    seeded_data,
    staff_headers,
):
    response = client.post(
        "/staff/prescriptions",
        headers=staff_headers,
        json={
            "patient_id": seeded_data["other_patient"].id,
            "exercise_id": seeded_data["exercise"].id,
            "repetitions_target": 12,
            "duration_limit_seconds": 120,
            "scheduled_days": "Tuesday, Thursday",
        },
    )

    assert response.status_code == 201
    prescription = response.json()
    assert prescription["id"] > 0
    assert prescription["patient_id"] == seeded_data["other_patient"].id
    assert prescription["staff_id"] == seeded_data["staff"].id
    assert prescription["exercise_id"] == seeded_data["exercise"].id
    assert prescription["repetitions_target"] == 12
    assert prescription["duration_limit_seconds"] == 120
    assert prescription["scheduled_days"] == "Tuesday, Thursday"
    assert prescription["is_active"] is True
    assert prescription["exercise"] == {
        "id": seeded_data["exercise"].id,
        "name": "Seated Knee Extension",
        "description": (
            "Sit upright, straighten one knee, then lower it."
        ),
    }


def test_staff_cannot_prescribe_to_non_patient(
    client,
    seeded_data,
    staff_headers,
):
    response = client.post(
        "/staff/prescriptions",
        headers=staff_headers,
        json={
            "patient_id": seeded_data["staff"].id,
            "exercise_id": seeded_data["exercise"].id,
            "repetitions_target": 10,
            "duration_limit_seconds": 90,
            "scheduled_days": "Monday",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Patient not found"


def test_staff_cannot_prescribe_inactive_exercise(
    client,
    seeded_data,
    staff_headers,
):
    response = client.post(
        "/staff/prescriptions",
        headers=staff_headers,
        json={
            "patient_id": seeded_data["patient"].id,
            "exercise_id": seeded_data["inactive_exercise"].id,
            "repetitions_target": 10,
            "duration_limit_seconds": 90,
            "scheduled_days": "Monday",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Active exercise not found"


def test_prescription_payload_validation_returns_422(
    client,
    seeded_data,
    staff_headers,
):
    response = client.post(
        "/staff/prescriptions",
        headers=staff_headers,
        json={
            "patient_id": seeded_data["patient"].id,
            "exercise_id": seeded_data["exercise"].id,
            "repetitions_target": 0,
            "duration_limit_seconds": 0,
            "scheduled_days": "Mo",
        },
    )

    assert response.status_code == 422
