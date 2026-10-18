from app.models import FlagType, StaffFlag


def _payload(seeded_data, **overrides):
    payload = {
        "client_session_id": "station-test-session-0001",
        "patient_id": seeded_data["patient"].id,
        "prescription_id": seeded_data["active_prescription"].id,
        "status": "completed",
        "repetitions_completed": 8,
        "duration_seconds": 95,
        "error_count": 1,
        "error_summary": "Keep your knee straight x1",
        "valid_repetitions": 8,
        "invalid_repetitions": 1,
        "incomplete_repetitions": 1,
        "arom_classification": "Within Normal Limits",
        "peak_rom_degrees": 78.5,
        "affected_side": "left",
        "device_recorded_at": "2026-10-18T01:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_station_uploads_session(client, staff_headers, seeded_data):
    response = client.post(
        "/staff/sessions", json=_payload(seeded_data), headers=staff_headers
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["valid_repetitions"] == 8
    assert body["arom_classification"] == "Within Normal Limits"
    assert body["prescription"]["exercise"]["name"] == "Seated Knee Extension"

    sessions = client.get(
        f"/staff/patients/{seeded_data['patient'].id}/sessions",
        headers=staff_headers,
    ).json()
    assert any(s["client_session_id"] == "station-test-session-0001" for s in sessions)


def test_station_upload_is_idempotent(client, staff_headers, seeded_data):
    first = client.post("/staff/sessions", json=_payload(seeded_data), headers=staff_headers)
    second = client.post("/staff/sessions", json=_payload(seeded_data), headers=staff_headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_station_upload_rejects_other_patients_prescription(client, staff_headers, seeded_data):
    payload = _payload(seeded_data, patient_id=seeded_data["other_patient"].id)
    response = client.post("/staff/sessions", json=payload, headers=staff_headers)
    assert response.status_code == 404


def test_station_upload_requires_staff(client, patient_headers, seeded_data):
    response = client.post("/staff/sessions", json=_payload(seeded_data), headers=patient_headers)
    assert response.status_code == 403


def test_station_upload_creates_compliance_flags(client, staff_headers, seeded_data, db):
    payload = _payload(
        seeded_data,
        client_session_id="station-test-session-0002",
        status="incomplete",
        repetitions_completed=2,
        valid_repetitions=2,
        invalid_repetitions=3,
    )
    response = client.post("/staff/sessions", json=payload, headers=staff_headers)
    assert response.status_code == 201, response.text
    types = {flag.flag_type for flag in db.query(StaffFlag).all()}
    assert FlagType.incomplete_session in types
    assert FlagType.repeated_error in types


def test_station_upload_validates_counts(client, staff_headers, seeded_data):
    payload = _payload(seeded_data, repetitions_completed=5)
    response = client.post("/staff/sessions", json=payload, headers=staff_headers)
    assert response.status_code == 422
