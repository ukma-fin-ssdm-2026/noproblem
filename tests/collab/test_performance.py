"""Перевірки часу синхронізації спільного редагування."""

from __future__ import annotations

from contextlib import ExitStack
from time import perf_counter

from fastapi.testclient import TestClient

from tests.api.helpers import sign_up
from tests.collab.helpers import Headers, joined, share, user_id


def test_paragraph_edit_reaches_nine_other_editors_under_one_second(
    client: TestClient,
    olena: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    """NFR-PERF-006: один edit доходить до решти 9 із 10 клієнтів < 1 с."""
    participants = [olena]
    for index in range(9):
        email = f"editor-{index}@example.com"
        participant = sign_up(client, email, f"Редактор {index}")
        share(client, olena, document_id, email, "editor")
        participants.append(participant)

    with ExitStack() as stack:
        sockets = []
        for participant in participants:
            socket = stack.enter_context(
                joined(client, document_id, participant)
            )
            sockets.append(socket)
            for existing in sockets[:-1]:
                assert existing.receive_json()["type"] == "presence"

        olena_id = user_id(client, olena)
        sockets[0].send_json(
            {"type": "lock.acquire", "paragraph_id": paragraph_id}
        )
        assert sockets[0].receive_json()["type"] == "lock.granted"
        for socket in sockets:
            assert socket.receive_json() == {
                "type": "lock.changed",
                "paragraph_id": paragraph_id,
                "user_id": olena_id,
            }

        started = perf_counter()
        sockets[0].send_json(
            {
                "type": "paragraph.edit",
                "paragraph_id": paragraph_id,
                "content": "Оновлений текст",
            }
        )
        for socket in sockets[1:]:
            assert socket.receive_json() == {
                "type": "paragraph.updated",
                "paragraph_id": paragraph_id,
                "content": "Оновлений текст",
                "author_id": olena_id,
            }
        elapsed = perf_counter() - started

    assert elapsed < 1.0
