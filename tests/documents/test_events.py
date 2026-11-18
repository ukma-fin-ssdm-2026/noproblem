"""Події DocumentService про зміни документа."""

from __future__ import annotations

from uuid import UUID

from src.documents.bootstrap import build_documents
from tests.conftest import IamTestEnv

OWNER = UUID("00000000-0000-0000-0000-000000000001")


class RecordingEvents:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, UUID]] = []

    def changed(self, document_id: int, kind: str, author_id: UUID) -> None:
        self.calls.append((document_id, kind, author_id))


def test_document_changes_notify_events(env: IamTestEnv) -> None:
    events = RecordingEvents()
    service = build_documents(
        env.access, clock=env.clock, events=events
    ).service
    document_id = service.create(OWNER, "key", "Звіт").document.id
    first = service.add_paragraph(OWNER, document_id, "A", None)
    second = service.add_paragraph(OWNER, document_id, "B", None)

    events.calls.clear()
    service.update_paragraph(
        OWNER, document_id, second.id, content="B updated", position=None
    )
    service.update_paragraph(
        OWNER, document_id, second.id, content=None, position=0
    )
    service.delete_paragraph(OWNER, document_id, first.id)
    service.rename(OWNER, document_id, "Новий звіт")
    service.move_to_trash(OWNER, document_id)

    assert events.calls == [
        (document_id, "paragraphs", OWNER),
        (document_id, "paragraphs", OWNER),
        (document_id, "title", OWNER),
        (document_id, "trashed", OWNER),
    ]
