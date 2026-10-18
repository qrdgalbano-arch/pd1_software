def test_dashboard_summary_returns_expected_counts_and_statuses(
    client,
    seeded_data,
    staff_headers,
):
    response = client.get(
        "/staff/dashboard/summary",
        headers=staff_headers,
    )

    assert response.status_code == 200
    summary = response.json()

    assert summary["patient_count"] == 2
    assert summary["active_prescription_count"] == 2
    assert summary["recent_session_count"] == 3
    assert summary["unresolved_flag_count"] == 2
    assert {
        item["status"]: item["count"]
        for item in summary["session_status_counts"]
    } == {
        "completed": 1,
        "incomplete": 1,
        "cancelled": 1,
    }
    assert sum(item["count"] for item in summary["recent_session_activity"]) == 3


def test_staff_searches_patients_by_name_and_email(
    client,
    seeded_data,
    staff_headers,
):
    name_response = client.get(
        "/staff/patients",
        params={"query": "demo"},
        headers=staff_headers,
    )
    email_response = client.get(
        "/staff/patients",
        params={"query": "other.patient@"},
        headers=staff_headers,
    )

    assert name_response.status_code == 200
    assert [patient["email"] for patient in name_response.json()] == [
        "patient@example.com",
    ]

    assert email_response.status_code == 200
    assert [patient["email"] for patient in email_response.json()] == [
        "other.patient@example.com",
    ]


def test_patient_prescriptions_include_exercise_context(
    client,
    seeded_data,
    staff_headers,
):
    patient_id = seeded_data["patient"].id

    response = client.get(
        f"/staff/patients/{patient_id}/prescriptions",
        headers=staff_headers,
    )

    assert response.status_code == 200
    prescriptions = response.json()
    assert len(prescriptions) == 2
    assert prescriptions[0]["is_active"] is True
    assert prescriptions[0]["exercise"] == {
        "id": seeded_data["exercise"].id,
        "name": "Seated Knee Extension",
        "description": (
            "Sit upright, straighten one knee, then lower it."
        ),
    }


def test_patient_sessions_include_prescription_and_exercise_context(
    client,
    seeded_data,
    staff_headers,
):
    patient_id = seeded_data["patient"].id

    response = client.get(
        f"/staff/patients/{patient_id}/sessions",
        headers=staff_headers,
    )

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 2
    assert sessions[0]["status"] == "completed"
    assert sessions[0]["repetitions_completed"] == 10
    assert sessions[0]["prescription"]["id"] == (
        seeded_data["active_prescription"].id
    )
    assert sessions[0]["prescription"]["exercise"]["name"] == (
        "Seated Knee Extension"
    )


def test_patient_sessions_honor_limit(
    client,
    seeded_data,
    staff_headers,
):
    response = client.get(
        f"/staff/patients/{seeded_data['patient'].id}/sessions",
        params={"limit": 1},
        headers=staff_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "completed"


def test_patient_flags_exclude_resolved_by_default_and_can_include_them(
    client,
    seeded_data,
    staff_headers,
):
    patient_id = seeded_data["patient"].id

    unresolved_response = client.get(
        f"/staff/patients/{patient_id}/flags",
        headers=staff_headers,
    )
    including_resolved_response = client.get(
        f"/staff/patients/{patient_id}/flags",
        params={"include_resolved": "true"},
        headers=staff_headers,
    )

    assert unresolved_response.status_code == 200
    unresolved_flags = unresolved_response.json()
    assert len(unresolved_flags) == 2
    assert all(flag["is_resolved"] is False for flag in unresolved_flags)
    assert all(flag["patient"]["id"] == patient_id for flag in unresolved_flags)

    assert including_resolved_response.status_code == 200
    assert len(including_resolved_response.json()) == 2


def test_dashboard_flags_filter_resolved_records_and_include_patient_context(
    client,
    seeded_data,
    staff_headers,
):
    unresolved_response = client.get(
        "/staff/flags",
        headers=staff_headers,
    )
    including_resolved_response = client.get(
        "/staff/flags",
        params={"include_resolved": "true"},
        headers=staff_headers,
    )

    assert unresolved_response.status_code == 200
    unresolved_flags = unresolved_response.json()
    assert len(unresolved_flags) == 2
    assert all(flag["is_resolved"] is False for flag in unresolved_flags)
    assert all(
        flag["patient"]["full_name"] == "Demo Patient"
        for flag in unresolved_flags
    )

    assert including_resolved_response.status_code == 200
    assert len(including_resolved_response.json()) == 3
    assert any(
        flag["is_resolved"] is True
        for flag in including_resolved_response.json()
    )


def test_patient_detail_routes_return_404_for_unknown_or_staff_ids(
    client,
    seeded_data,
    staff_headers,
):
    paths = [
        "/staff/patients/999999/prescriptions",
        "/staff/patients/999999/sessions",
        "/staff/patients/999999/flags",
        f"/staff/patients/{seeded_data['staff'].id}/prescriptions",
        f"/staff/patients/{seeded_data['staff'].id}/sessions",
        f"/staff/patients/{seeded_data['staff'].id}/flags",
    ]

    for path in paths:
        response = client.get(path, headers=staff_headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Patient not found"
