"""Наскрізні сценарії блокувань між WebSocket і REST."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.helpers import paragraphs_url
from tests.collab.helpers import (
    Headers,
    joined,
    share,
    user_id,
)


def test_lock_conflict_then_takeover_after_holder_disconnects(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    """FR-024/I-08: REST відхиляє зміну під чужим lock, disconnect звільняє."""
    share(client, olena, document_id, "petro@example.com", "editor")
    olena_id = user_id(client, olena)
    petro_id = user_id(client, petro)
    paragraph_url = f"{paragraphs_url(document_id)}/{paragraph_id}"

    with joined(client, document_id, petro) as ws_petro:
        with joined(client, document_id, olena) as ws_olena:
            assert ws_petro.receive_json() == {
                "type": "presence",
                "user_id": olena_id,
                "name": "Олена",
                "status": "joined",
            }

            ws_olena.send_json(
                {"type": "lock.acquire", "paragraph_id": paragraph_id}
            )
            assert ws_olena.receive_json() == {
                "type": "lock.granted",
                "paragraph_id": paragraph_id,
            }
            locked = {
                "type": "lock.changed",
                "paragraph_id": paragraph_id,
                "user_id": olena_id,
            }
            assert ws_olena.receive_json() == locked
            assert ws_petro.receive_json() == locked

            ws_petro.send_json(
                {"type": "lock.acquire", "paragraph_id": paragraph_id}
            )
            assert ws_petro.receive_json() == {
                "type": "lock.denied",
                "paragraph_id": paragraph_id,
                "holder": olena_id,
                "reason": "locked",
            }

            response = client.patch(
                paragraph_url,
                json={"content": "Зміна від Петра"},
                headers=petro,
            )
            assert response.status_code == 409

        assert ws_petro.receive_json() == {
            "type": "lock.changed",
            "paragraph_id": paragraph_id,
            "user_id": None,
        }
        left = ws_petro.receive_json()
        assert (left["type"], left["status"]) == ("presence", "left")

        ws_petro.send_json(
            {"type": "lock.acquire", "paragraph_id": paragraph_id}
        )
        assert ws_petro.receive_json() == {
            "type": "lock.granted",
            "paragraph_id": paragraph_id,
        }
        assert ws_petro.receive_json() == {
            "type": "lock.changed",
            "paragraph_id": paragraph_id,
            "user_id": petro_id,
        }
