"""NFR-PERF-002: document rename latency."""

import uuid

from locust import HttpUser, between, events, task
from locust.exception import StopUser

from loadtests.nfr import (
    API,
    check_nfr_threshold,
    create_document,
    register_user,
)

MAX_RESPONSE_TIME_MS = 1_000


class RenameUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        if register_user(self.client, "Rename Load User") is None:
            raise StopUser()
        self.document_id = create_document(
            self.client,
            "Document for rename",
            "POST /documents (rename setup)",
        )
        if self.document_id is None:
            raise StopUser()

    @task
    def rename(self) -> None:
        with self.client.put(
            f"{API}/documents/{self.document_id}",
            json={"title": f"Renamed {uuid.uuid4().hex[:8]}"},
            name="PUT /documents/{id} (rename)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Rename failed: HTTP {response.status_code}")


@events.quitting.add_listener
def check_rename_threshold(environment, **_) -> None:
    check_nfr_threshold(
        environment,
        requirement="NFR-PERF-002",
        request_name="PUT /documents/{id} (rename)",
        method="PUT",
        threshold_ms=MAX_RESPONSE_TIME_MS,
    )
