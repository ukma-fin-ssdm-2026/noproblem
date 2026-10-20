"""Tests for IAM adapters."""

from __future__ import annotations

import logging

import pytest

from src.iam.adapters import LoggingEmailSender
from src.iam.ports import EmailMessage


# RED test for LoggingEmailSender: it should not log sensitive information like unlock tokens.
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


# PS: File made with Claude assistance and reviewed by Olha Marushchenko
