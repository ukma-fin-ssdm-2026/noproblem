"""Навантажувальний сценарій Notely (Locust).

SLO: p95 затримки не більше 150 мс. Якщо p95 вищий, процес
завершується з ненульовим кодом (це використовує CI).

Змінні оточення:
    WITH_AUTH=1  кожен віртуальний користувач один раз реєструється
                 і надсилає Bearer-токен (за замовчуванням вимкнено,
                 бо /documents зараз не вимагає автентифікації).
"""

import os
import uuid

from locust import HttpUser, between, events, task

SLO_P95_MS = 150
API = "/api/v1"
WITH_AUTH = os.getenv("WITH_AUTH") == "1"


class NotelyUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        if not WITH_AUTH:
            return
        suffix = uuid.uuid4().hex[:12]
        response = self.client.post(
            f"{API}/auth/register",
            json={
                "email": f"load-{suffix}@example.com",
                "name": "Load User",
                "password": "load-test-password",
            },
            name="POST /auth/register",
        )
        if response.status_code == 201:
            token = response.json()["access_token"]
            self.client.headers["Authorization"] = f"Bearer {token}"

    @task(5)
    def list_documents(self):
        self.client.get(f"{API}/documents", name="GET /documents")

    @task(3)
    def read_demo_document(self):
        self.client.get(f"{API}/documents/1", name="GET /documents/{id}")

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
        """Той самий ключ двічі: другий виклик має бути
        ідемпотентним повтором."""
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
    if failures > 0 or (p95 is not None and p95 > SLO_P95_MS):
        environment.process_exit_code = 1
