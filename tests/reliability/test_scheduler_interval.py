"""Граничний тест: інтервал планувальника з ``TRASH_PURGE_INTERVAL_S``.

Хибне значення має зупиняти застосунок під час запуску (швидка
відмова), а не тихо вимикати очищення кошика.
"""

from __future__ import annotations

import pytest

from src.scheduler.loop import (
    DEFAULT_TRASH_PURGE_INTERVAL_S,
    TRASH_PURGE_INTERVAL_ENV,
    trash_purge_interval_from_env,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", DEFAULT_TRASH_PURGE_INTERVAL_S),
        ("   ", DEFAULT_TRASH_PURGE_INTERVAL_S),
        ("0", None),
        ("0.5", 0.5),
        (" 30 ", 30.0),
    ],
    ids=["unset", "blank", "zero-disables", "fraction", "spaces"],
)
def test_valid_values(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float | None
) -> None:
    monkeypatch.setenv(TRASH_PURGE_INTERVAL_ENV, raw)
    assert trash_purge_interval_from_env() == expected


def test_missing_variable_means_hourly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TRASH_PURGE_INTERVAL_ENV, raising=False)
    assert trash_purge_interval_from_env() == 3600.0


@pytest.mark.parametrize(
    "raw",
    ["abc", "-1", "-0.001", "nan", "inf", "-inf"],
)
def test_invalid_values_fail_fast(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(TRASH_PURGE_INTERVAL_ENV, raw)
    with pytest.raises(ValueError, match=TRASH_PURGE_INTERVAL_ENV):
        trash_purge_interval_from_env()


# File was created by Claude. Reviewed by Kozynska Anastasia
