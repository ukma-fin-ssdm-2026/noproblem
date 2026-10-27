"""Tests for IAM adapters."""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from src.iam.adapters import InMemoryAccessRepository, LoggingEmailSender
from src.iam.models import DocumentAccess, Role
from src.iam.ports import EmailMessage


# RED test: LoggingEmailSender should not log sensitive information like
# unlock tokens.
def test_logging_email_sender_does_not_log_unlock_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = "test-secret-unlock-token"
    message = EmailMessage(
        recipient="olena@example.com",
        subject="Account locked",
        body=f"Unlock your account: https://example.test/unlock?token={token}",
    )

    with caplog.at_level(logging.WARNING, logger="notely.email"):
        LoggingEmailSender().send(message)

    assert token not in caplog.text


def test_access_repository_ensure_does_not_replace_existing_role() -> None:
    repository = InMemoryAccessRepository()
    user_id = uuid4()
    guest = DocumentAccess(document_id=1, user_id=user_id, role=Role.GUEST)
    editor = DocumentAccess(document_id=1, user_id=user_id, role=Role.EDITOR)

    repository.save(editor)

    assert repository.ensure(guest) == editor


# PS: File made with Claude assistance and reviewed by Olha Marushchenko
