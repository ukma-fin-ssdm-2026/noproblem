"""Інтеграційні тести HTTP-адаптера ``/api/v1/auth``.

Перевіряють те, що бачить клієнт: статус-коди, тексти помилок,
заголовки та схему OpenAPI. Бізнес-правила детально перевіряє
``tests/iam/test_authentication.py``. Тут достатньо переконатися, що
адаптер правильно їх «перекладає» на HTTP.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from tests.conftest import (
    VALID_EMAIL,
    VALID_NAME,
    VALID_PASSWORD,
    IamTestEnv,
)

BASE = "/api/v1/auth"
REGISTER_BODY = {
    "email": VALID_EMAIL,
    "name": VALID_NAME,
    "password": VALID_PASSWORD,
}
WRONG_LOGIN = {"email": VALID_EMAIL, "password": "wrong-password"}


@pytest.fixture
def client(env: IamTestEnv) -> TestClient:
    return TestClient(create_app(iam=env.iam, access=env.access))


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(client: TestClient) -> str:
    response = client.post(f"{BASE}/register", json=REGISTER_BODY)
    assert response.status_code == 201
    return response.json()["access_token"]


class TestRegister:
    def test_returns_201_with_token_and_public_user(
        self, client: TestClient
    ) -> None:
        response = client.post(f"{BASE}/register", json=REGISTER_BODY)
        assert response.status_code == 201
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == VALID_EMAIL
        assert set(body["user"]) == {"id", "email", "name", "created_at"}
        assert "password" not in response.text

    def test_short_password_gives_specific_message(
        self, client: TestClient
    ) -> None:
        """FR-002: повідомлення з конкретною причиною."""
        body = {**REGISTER_BODY, "password": "1234567"}
        response = client.post(f"{BASE}/register", json=body)
        assert response.status_code == 422
        assert response.json() == {
            "detail": "Пароль має містити щонайменше 8 символів."
        }

    def test_taken_email_gives_409(self, client: TestClient) -> None:
        register(client)
        response = client.post(f"{BASE}/register", json=REGISTER_BODY)
        assert response.status_code == 409
        assert "уже зареєстрований" in response.json()["detail"]

    def test_missing_field_uses_project_wide_422(
        self, client: TestClient
    ) -> None:
        response = client.post(f"{BASE}/register", json={"email": "a@b.co"})
        assert response.status_code == 422
        assert response.json() == {"detail": "Некоректні вхідні дані."}


class TestLogin:
    def test_success(self, client: TestClient) -> None:
        register(client)
        response = client.post(
            f"{BASE}/login",
            json={"email": VALID_EMAIL, "password": VALID_PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_wrong_password_gives_generic_401(
        self, client: TestClient
    ) -> None:
        """FR-004: точний текст із вимог, без уточнень."""
        register(client)
        response = client.post(f"{BASE}/login", json=WRONG_LOGIN)
        assert response.status_code == 401
        assert response.json() == {"detail": "Невірний email або пароль"}
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_unknown_email_is_indistinguishable(
        self, client: TestClient
    ) -> None:
        register(client)
        wrong = client.post(f"{BASE}/login", json=WRONG_LOGIN)
        unknown = client.post(
            f"{BASE}/login",
            json={"email": "nobody@example.com", "password": "whatever1"},
        )
        assert (unknown.status_code, unknown.json()) == (
            wrong.status_code,
            wrong.json(),
        )

    def test_lockout_gives_423_with_retry_after(
        self, client: TestClient
    ) -> None:
        """Діаграма послідовності: 5-та спроба — 401, далі — 423."""
        register(client)
        statuses = [
            client.post(f"{BASE}/login", json=WRONG_LOGIN).status_code
            for _ in range(6)
        ]
        assert statuses == [401, 401, 401, 401, 401, 423]
        locked = client.post(f"{BASE}/login", json=WRONG_LOGIN)
        assert locked.headers["Retry-After"] == str(15 * 60)


class TestProtectedRoutes:
    def test_me_without_token_is_401(self, client: TestClient) -> None:
        response = client.get(f"{BASE}/me")
        assert response.status_code == 401
        assert response.json() == {"detail": "Потрібна автентифікація."}
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_me_with_unknown_token_is_401(self, client: TestClient) -> None:
        response = client.get(f"{BASE}/me", headers=bearer("forged"))
        assert response.status_code == 401

    def test_me_with_valid_token(self, client: TestClient) -> None:
        token = register(client)
        response = client.get(f"{BASE}/me", headers=bearer(token))
        assert response.status_code == 200
        assert response.json()["email"] == VALID_EMAIL

    def test_logout_then_token_is_rejected(self, client: TestClient) -> None:
        """Test-13 / FR-006."""
        token = register(client)
        logout = client.post(f"{BASE}/logout", headers=bearer(token))
        assert logout.status_code == 204
        response = client.get(f"{BASE}/me", headers=bearer(token))
        assert response.status_code == 401


class TestUnlock:
    def test_unlock_flow(self, client: TestClient, env: IamTestEnv) -> None:
        register(client)
        for _ in range(5):
            client.post(f"{BASE}/login", json=WRONG_LOGIN)
        token = env.mail.last_unlock_token()
        response = client.post(f"{BASE}/unlock", json={"token": token})
        assert response.status_code == 204
        login = client.post(
            f"{BASE}/login",
            json={"email": VALID_EMAIL, "password": VALID_PASSWORD},
        )
        assert login.status_code == 200

    def test_invalid_token_is_400(self, client: TestClient) -> None:
        response = client.post(f"{BASE}/unlock", json={"token": "nope"})
        assert response.status_code == 400


class TestIntegrationWithExistingApi:
    def test_document_routes_require_token(self, client: TestClient) -> None:
        """Маршрути документів тепер захищені (FR-046, NFR-SEC-001)."""
        response = client.get("/api/v1/documents")
        assert response.status_code == 401
        token = register(client)
        response = client.get("/api/v1/documents", headers=bearer(token))
        assert response.status_code == 200

    def test_openapi_marks_protected_routes(self, client: TestClient) -> None:
        """Атрибут якості 2.2: захищені маршрути мають 401 і security."""
        spec = client.get("/openapi.json").json()
        for path, method in [("/me", "get"), ("/logout", "post")]:
            operation = spec["paths"][f"{BASE}{path}"][method]
            assert operation["security"] == [{"HTTPBearer": []}]
            assert "401" in operation["responses"]
        public = spec["paths"][f"{BASE}/login"]["post"]
        assert "security" not in public


# File was created by Claude. Reviewed by Kozynska Anastasia
