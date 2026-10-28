"""Shared setup and threshold checks for NFR Locust scenarios."""

from __future__ import annotations

import uuid

from locust.clients import HttpSession
from locust.env import Environment

API = "/api/v1"
PASSWORD = "load-test-password"


def register_user(client: HttpSession, name: str) -> str | None:
    email = f"locust-{uuid.uuid4().hex}@example.com"
    with client.post(
        f"{API}/auth/register",
        json={"email": email, "name": name, "password": PASSWORD},
        name="POST /auth/register (setup)",
        catch_response=True,
    ) as response:
        if response.status_code != 201:
            response.failure(
                f"Registration failed: HTTP {response.status_code}"
            )
            return None
        try:
            body = response.json()
        except ValueError:
            response.failure("Registration returned invalid JSON")
            return None
        if not isinstance(body, dict) or not body.get("access_token"):
            response.failure("Registration response has no access token")
            return None
        client.headers["Authorization"] = f"Bearer {body['access_token']}"
    return email


def create_document(
    client: HttpSession,
    title: str,
    request_name: str,
) -> int | None:
    with client.post(
        f"{API}/documents",
        json={"title": title},
        headers={"Idempotency-Key": str(uuid.uuid4())},
        name=request_name,
        catch_response=True,
    ) as response:
        if response.status_code != 201:
            response.failure(
                f"Document creation failed: HTTP {response.status_code}"
            )
            return None
        try:
            body = response.json()
        except ValueError:
            response.failure("Document creation returned invalid JSON")
            return None
        document_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(document_id, int):
            response.failure("Document creation response has no id")
            return None
    return document_id


def check_nfr_threshold(
    environment: Environment,
    *,
    requirement: str,
    request_name: str,
    method: str,
    threshold_ms: int,
) -> bool:
    stats = environment.stats.get(request_name, method)
    median_ms = stats.get_response_time_percentile(0.50)
    p95_ms = stats.get_response_time_percentile(0.95)
    p99_ms = stats.get_response_time_percentile(0.99)
    max_ms = stats.max_response_time
    failures = environment.stats.total.num_failures
    passed = (
        stats.num_requests > 0
        and p95_ms is not None
        and p95_ms <= threshold_ms
        and failures == 0
    )

    print(
        f"{requirement}: median={median_ms} ms, p95={p95_ms} ms, "
        f"p99={p99_ms} ms, max={max_ms} ms; "
        f"threshold p95 <= {threshold_ms} ms; "
        f"requests={stats.num_requests}, failures={failures}; "
        f"{'PASS' if passed else 'FAIL'}"
    )
    if not passed:
        environment.process_exit_code = 1
    return passed


# p.s. The file made with Copilot assistance and reviewed by Olha Bidochka
