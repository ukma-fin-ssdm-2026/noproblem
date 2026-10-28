"""NFR-PERF-005: search latency with 100 documents in each workspace."""

from locust import HttpUser, between, events, task
from locust.exception import StopUser

from loadtests.nfr import (
    API,
    check_nfr_threshold,
    create_document,
    register_user,
)

DOCUMENT_COUNT = 100
SEARCH_TERM = "locustsearch"
MAX_RESPONSE_TIME_MS = 2_000


class SearchUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        if register_user(self.client, "Search Load User") is None:
            raise StopUser()

        for index in range(DOCUMENT_COUNT):
            document_id = create_document(
                self.client,
                f"{SEARCH_TERM} document {index + 1}",
                "POST /documents (search setup)",
            )
            if document_id is None:
                raise StopUser()

        with self.client.get(
            f"{API}/documents",
            params={"limit": DOCUMENT_COUNT},
            name="GET /documents (search setup verification)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    "Workspace verification failed: "
                    f"HTTP {response.status_code}"
                )
                raise StopUser()
            try:
                body = response.json()
            except ValueError:
                response.failure(
                    "Workspace verification returned invalid JSON"
                )
                raise StopUser()
            pagination = (
                body.get("pagination") if isinstance(body, dict) else None
            )
            if (
                not isinstance(pagination, dict)
                or pagination.get("total") != DOCUMENT_COUNT
            ):
                response.failure(
                    f"Expected exactly {DOCUMENT_COUNT} workspace documents"
                )
                raise StopUser()

    @task
    def search(self) -> None:
        with self.client.get(
            f"{API}/search",
            params={"q": SEARCH_TERM},
            name="GET /search",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Search failed: HTTP {response.status_code}")
                return
            try:
                results = response.json()
            except ValueError:
                response.failure("Search returned invalid JSON")
                return
            if not isinstance(results, list) or not results:
                response.failure("Search returned no matching documents")


@events.quitting.add_listener
def check_search_threshold(environment, **_) -> None:
    check_nfr_threshold(
        environment,
        requirement="NFR-PERF-005",
        request_name="GET /search",
        method="GET",
        threshold_ms=MAX_RESPONSE_TIME_MS,
    )


# p.s. The file made with Copilot assistance and reviewed by Olha Bidochka
