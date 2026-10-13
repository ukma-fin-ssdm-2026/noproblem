"""Навантажувальний сценарій Notely (Locust).

Кожен віртуальний користувач при старті реєструється й створює власний
документ, а далі працює тільки з ним (ендпоінти потребують токена і ролі).
Реєстрація виконується окремо від статистики Locust, щоб повільне
хешування паролів не спотворювало вимірювання затримки API.

SLO: p95 затримки не більше 150 мс (змінна SLO_P95_MS). Якщо p95 вищий
або були помилки, процес завершується з ненульовим кодом.
"""

import json
import os
import uuid

import requests
from locust import HttpUser, between, events, task
from locust.exception import StopUser

SLO_P95_MS = int(os.getenv("SLO_P95_MS", "150"))
API = "/api/v1"
PASSWORD = "load-test-password"


class NotelyUser(HttpUser):
    wait_time = between(0.5, 1.5)
    document_id = None

    def on_start(self):
        base = self.host.rstrip("/") + API
        email = f"load-{uuid.uuid4().hex[:12]}@example.com"
        registered = requests.post(
            f"{base}/auth/register",
            json={"email": email, "name": "Load User", "password": PASSWORD},
            timeout=30,
        )
        if registered.status_code != 201:
            print(
                print(
                    "Реєстрація не вдалась: "
                    f"{registered.status_code} {registered.text[:100]}"
                )
            )
            raise StopUser()
        token = registered.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"

        created = requests.post(
            f"{base}/documents",
            json={"title": "Документ для навантаження"},
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
            timeout=30,
        )
        if created.status_code != 201:
            print(f"Створення документа не вдалось: {created.status_code}")
            raise StopUser()
        self.document_id = created.json()["id"]

    @task(5)
    def list_documents(self):
        self.client.get(f"{API}/documents", name="GET /documents")

    @task(3)
    def read_own_document(self):
        self.client.get(
            f"{API}/documents/{self.document_id}", name="GET /documents/{id}"
        )

    @task(2)
    def create_document(self):
        self.client.post(
            f"{API}/documents",
            json={"title": "Навантажувальний тест"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
            name="POST /documents",
        )

    @task(1)
    def create_document_with_replay(self):
        """Той самий ключ двічі.

        Другий виклик має бути ідемпотентним повтором.
        """
        key = str(uuid.uuid4())
        for _ in range(2):
            self.client.post(
                f"{API}/documents",
                json={"title": "Повтор"},
                headers={"Idempotency-Key": key},
                name="POST /documents (replay)",
            )


@events.quitting.add_listener
def check_slo(environment, **_):
    p95 = environment.stats.total.get_response_time_percentile(0.95)
    failures = environment.stats.total.num_failures
    print(f"p95 = {p95} мс (поріг {SLO_P95_MS} мс), помилок: {failures}")
    replay = environment.stats.get("POST /documents (replay)", "POST")
    summary = {
        "requests": environment.stats.total.num_requests,
        "failures": failures,
        "p95_ms": p95,
        "replay_requests": replay.num_requests,
    }
    with open("loadtests/last_run.json", "w", encoding="utf-8") as f:
        json.dump(summary, f)
    if failures > 0 or (p95 is not None and p95 > SLO_P95_MS):
        environment.process_exit_code = 1
