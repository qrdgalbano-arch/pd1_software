import jwt

from app.core.config import settings


def test_login_returns_access_and_refresh_tokens(client, seeded_data):
    response = client.post(
        "/auth/login",
        data={
            "username": "staff@example.com",
            "password": "staff-password",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    access_payload = jwt.decode(
        body["access_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    refresh_payload = jwt.decode(
        body["refresh_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert access_payload["sub"] == str(seeded_data["staff"].id)
    assert access_payload["role"] == "staff"
    assert access_payload["type"] == "access"
    assert refresh_payload["sub"] == str(seeded_data["staff"].id)
    assert refresh_payload["type"] == "refresh"


def test_login_rejects_invalid_password(client, seeded_data):
    response = client.post(
        "/auth/login",
        data={
            "username": "staff@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_inactive_user(client, seeded_data):
    response = client.post(
        "/auth/login",
        data={
            "username": "inactive.patient@example.com",
            "password": "inactive-password",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "User account is inactive"


def test_me_returns_authenticated_identity(client, seeded_data, staff_headers):
    response = client.get("/auth/me", headers=staff_headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": seeded_data["staff"].id,
        "full_name": "Demo Rehabilitation Staff",
        "email": "staff@example.com",
        "role": "staff",
    }


def test_me_rejects_missing_or_invalid_access_token(client, seeded_data):
    missing_token_response = client.get("/auth/me")
    invalid_token_response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert missing_token_response.status_code == 401
    assert invalid_token_response.status_code == 401


def test_refresh_issues_new_token_pair(client, seeded_data, login):
    original_tokens = login("patient@example.com", "patient-password")

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": original_tokens["refresh_token"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


def test_refresh_rejects_access_token(client, seeded_data, login):
    tokens = login("patient@example.com", "patient-password")

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate refresh token"
