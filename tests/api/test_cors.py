"""CORS policy for the browser frontend."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import main


def test_cors_preflight_allows_configured_origin_and_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "load_env_file", lambda: False)
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://notely.example, http://localhost:3000",
    )
    client = TestClient(main.create_app())

    response = client.options(
        "/api/v1/documents",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "authorization,content-type,idempotency-key"
            ),
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://localhost:3000"
    )
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers
    assert "idempotency-key" in allowed_headers


def test_cors_exposes_lockout_retry_after_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "load_env_file", lambda: False)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    client = TestClient(main.create_app())

    response = client.get(
        "/api/v1/auth/me",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 401
    assert response.headers["access-control-expose-headers"] == "Retry-After"


def test_cors_rejects_unconfigured_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "load_env_file", lambda: False)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    client = TestClient(main.create_app())

    response = client.options(
        "/api/v1/documents",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_rejects_wildcard_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "load_env_file", lambda: False)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        main.create_app()


# p.s. File was created by Copilot and reviewed by Olha Bidochka