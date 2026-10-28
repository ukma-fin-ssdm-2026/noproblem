"""NFR-PERF-003: document restore latency."""

from locust import HttpUser, between, events, task
from locust.exception import StopUser

from loadtests.nfr import (
    API,
    check_nfr_threshold,
    create_document,
    register_user,
)

MAX_RESPONSE_TIME_MS = 2_000


class RestoreUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        if register_user(self.client, "Restore Load User") is None:
            raise StopUser()

    @task
    def restore_from_trash(self) -> None:
        document_id = create_document(
            self.client,
            "Document for restore",
            "POST /documents (restore setup)",
        )
        if document_id is None:
            return

        with self.client.delete(
            f"{API}/documents/{document_id}",
            name="DELETE /documents/{id} (restore setup)",
            catch_response=True,
        ) as response:
            if response.status_code != 204:
                response.failure(
                    f"Moving document to trash failed: "
                    f"HTTP {response.status_code}"
                )
                return

        with self.client.post(
            f"{API}/documents/{document_id}/restore",
            name="POST /documents/{id}/restore",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Restore failed: HTTP {response.status_code}"
                )


@events.quitting.add_listener
def check_restore_threshold(environment, **_) -> None:
    check_nfr_threshold(
        environment,
        requirement="NFR-PERF-003",
        request_name="POST /documents/{id}/restore",
        method="POST",
        threshold_ms=MAX_RESPONSE_TIME_MS,
    )

#p.s. The file made with Copilot assistance and reviewed by Olha Bidochka