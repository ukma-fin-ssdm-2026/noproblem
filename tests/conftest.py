"""Спільні фікстури pytest."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.iam import AuthService, build_iam
from tests.fakes import FakeClock, FakePasswordHasher, RecordingEmailSender

VALID_EMAIL = "olena@example.com"
VALID_NAME = "Олена"
VALID_PASSWORD = "correct-horse"  # nosec B105 — тестові дані


@dataclass
class IamTestEnv:
    """Сервіс IAM разом із підробками, якими тест керує."""

    iam: AuthService
    clock: FakeClock
    hasher: FakePasswordHasher
    mail: RecordingEmailSender


@pytest.fixture
def env() -> IamTestEnv:
    clock = FakeClock()
    hasher = FakePasswordHasher()
    mail = RecordingEmailSender()
    iam = build_iam(clock=clock, password_hasher=hasher, email_sender=mail)
    return IamTestEnv(iam=iam, clock=clock, hasher=hasher, mail=mail)


# File was created by Claude. Reviewed by Kozynska Anastasia
