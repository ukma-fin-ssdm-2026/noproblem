"""Вимірювання часу успішної автентифікації через Locust."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import NotRequired, TypedDict

import requests
from locust import HttpUser, constant, events, task
from locust.exception import StopUser


class LoginResult(TypedDict):
    attempt: int
    status_code: int | None
    duration_ms: float
    success: bool
    error: NotRequired[str]


API = "/api/v1"
ATTEMPTS = 30
PASSWORD = "load-test-password"
MAX_RESPONSE_TIME_MS = 2_000
LOGIN_RESULTS: list[LoginResult] = []


class AuthenticationUser(HttpUser):
    wait_time = constant(0)

    def on_start(self) -> None:
        self.email = f"auth-load-{uuid.uuid4().hex}@example.com"
        try:
            registered = requests.post(
                f"{self.host.rstrip('/')}{API}/auth/register",
                json={
                    "email": self.email,
                    "name": "Authentication Load User",
                    "password": PASSWORD,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            print(f"Реєстрація для тесту входу не вдалась: {exc}")
            self.environment.runner.quit()
            raise StopUser() from exc

        if registered.status_code != 201:
            print(
                "Реєстрація для тесту входу не вдалась: "
                f"{registered.status_code} {registered.text[:100]}"
            )
            self.environment.runner.quit()
            raise StopUser()

    @task
    def measure_login(self) -> None:
        for attempt in range(1, ATTEMPTS + 1):
            started = time.perf_counter()
            try:
                with self.client.post(
                    f"{API}/auth/login",
                    json={"email": self.email, "password": PASSWORD},
                    name="POST /auth/login",
                    timeout=30,
                    catch_response=True,
                ) as response:
                    duration_ms = round(
                        (time.perf_counter() - started) * 1_000, 2
                    )
                    try:
                        body = response.json()
                        success = (
                            response.status_code == 200
                            and isinstance(body, dict)
                            and bool(body.get("access_token"))
                        )
                    except ValueError:
                        success = False

                    LOGIN_RESULTS.append(
                        {
                            "attempt": attempt,
                            "status_code": response.status_code,
                            "duration_ms": duration_ms,
                            "success": success,
                        }
                    )
                    if not success:
                        response.failure(
                            "Expected HTTP 200 with an access token"
                        )
            except requests.RequestException as exc:
                duration_ms = round((time.perf_counter() - started) * 1_000, 2)
                LOGIN_RESULTS.append(
                    {
                        "attempt": attempt,
                        "status_code": None,
                        "duration_ms": duration_ms,
                        "success": False,
                        "error": str(exc),
                    }
                )

        self.environment.runner.quit()


@events.quitting.add_listener
def check_authentication_slo(environment, **_) -> None:
    max_response_time_ms = max(
        (result["duration_ms"] for result in LOGIN_RESULTS),
        default=None,
    )
    successful_requests = sum(
        result["success"] is True for result in LOGIN_RESULTS
    )
    passed = (
        len(LOGIN_RESULTS) == ATTEMPTS
        and successful_requests == ATTEMPTS
        and max_response_time_ms is not None
        and max_response_time_ms <= MAX_RESPONSE_TIME_MS
    )
    report = {
        "requests": len(LOGIN_RESULTS),
        "successful_requests": successful_requests,
        "max_response_time_ms": max_response_time_ms,
        "threshold_ms": MAX_RESPONSE_TIME_MS,
        "passed": passed,
        "results": LOGIN_RESULTS,
    }
    Path("loadtests/auth_last_run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Успішних входів: {successful_requests}/{ATTEMPTS}; "
        f"максимальний час: {max_response_time_ms} мс "
        f"(поріг {MAX_RESPONSE_TIME_MS} мс)"
    )
    if not passed:
        environment.process_exit_code = 1


# PS: File made with Copilot assistance and reviewed by Olha Marushchenko
