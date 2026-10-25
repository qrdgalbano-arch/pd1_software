import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/staff/patients",
        "/staff/exercises",
        "/staff/flags",
        "/staff/dashboard/summary",
    ],
)
def test_staff_routes_reject_unauthenticated_requests(client, path):
    response = client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/staff/patients",
        "/staff/exercises",
        "/staff/flags",
        "/staff/dashboard/summary",
    ],
)
def test_staff_routes_reject_patient_role(
    client,
    seeded_data,
    patient_headers,
    path,
):
    response = client.get(path, headers=patient_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_staff_can_list_patients(client, seeded_data, staff_headers):
    response = client.get("/staff/patients", headers=staff_headers)

    assert response.status_code == 200

    patients = response.json()
    assert [patient["email"] for patient in patients] == [
        "patient@example.com",
        "inactive.patient@example.com",
        "other.patient@example.com",
    ]
    assert all(
        {"id", "full_name", "email"} <= set(patient)
        for patient in patients
    )


def test_patient_can_only_access_own_prescriptions(
    client,
    seeded_data,
    patient_headers,
):
    response = client.get(
        "/patients/me/prescriptions",
        headers=patient_headers,
    )

    assert response.status_code == 200

    prescriptions = response.json()
    assert len(prescriptions) == 1
    assert prescriptions[0]["id"] == seeded_data["active_prescription"].id
    assert prescriptions[0]["patient_id"] == seeded_data["patient"].id
    assert prescriptions[0]["is_active"] is True
    assert prescriptions[0]["exercise"]["name"] == "Seated Knee Extension"


def test_patient_route_rejects_staff_role(client, seeded_data, staff_headers):
    response = client.get(
        "/patients/me/prescriptions",
        headers=staff_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
