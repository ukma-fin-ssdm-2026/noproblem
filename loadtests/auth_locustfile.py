"""NFR-PERF-004: успішний вхід має вкладатися в поріг p95."""

from __future__ import annotations

import json
from pathlib import Path

from locust import HttpUser, constant, events, task
from locust.exception import StopUser

from loadtests.nfr import (
    API,
    check_nfr_threshold,
    register_user,
)

ATTEMPTS = 30
MAX_RESPONSE_TIME_MS = 2_000


class AuthenticationUser(HttpUser):
    wait_time = constant(0)

    def on_start(self) -> None:
        self.email = register_user(self.client, "Authentication Load User")
        if self.email is None:
            raise StopUser()

    @task
    def measure_login(self) -> None:
        for _ in range(ATTEMPTS):
            with self.client.post(
                f"{API}/auth/login",
                json={
                    "email": self.email,
                    "password": "load-test-password",
                },
                name="POST /auth/login",
                catch_response=True,
            ) as response:
                if response.status_code != 200:
                    response.failure(
                        f"Login failed: HTTP {response.status_code}"
                    )
                else:
                    try:
                        body = response.json()
                    except ValueError:
                        response.failure("Login returned invalid JSON")
                    else:
                        if not isinstance(body, dict) or not body.get(
                            "access_token"
                        ):
                            response.failure(
                                "Login response has no access token"
                            )

        self.environment.runner.quit()


@events.quitting.add_listener
def check_authentication_slo(environment, **_) -> None:
    passed = check_nfr_threshold(
        environment,
        requirement="NFR-PERF-004",
        request_name="POST /auth/login",
        method="POST",
        threshold_ms=MAX_RESPONSE_TIME_MS,
    )
    stats = environment.stats.get("POST /auth/login", "POST")
    passed = passed and stats.num_requests == ATTEMPTS
    report = {
        "requests": stats.num_requests,
        "successful_requests": stats.num_requests - stats.num_failures,
        "median_response_time_ms": stats.get_response_time_percentile(0.50),
        "p95_response_time_ms": stats.get_response_time_percentile(0.95),
        "p99_response_time_ms": stats.get_response_time_percentile(0.99),
        "max_response_time_ms": stats.max_response_time,
        "threshold_ms": MAX_RESPONSE_TIME_MS,
        "passed": passed,
    }
    Path("loadtests/auth_last_run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Успішних входів: {report['successful_requests']}/{ATTEMPTS}; "
        f"p95: {report['p95_response_time_ms']} мс "
        f"(поріг {MAX_RESPONSE_TIME_MS} мс)"
    )
    if not passed:
        environment.process_exit_code = 1


# PS: File made with Copilot assistance and reviewed by Olha Marushchenko
