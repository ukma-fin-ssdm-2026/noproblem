"""Перевірки попередження про сховище в памʼяті"""

from __future__ import annotations

import logging

import pytest

from src.api import main

DATABASE_WARNING = (
    "DATABASE_URL не задано: дані зберігаються в памʼяті й зникнуть "
    "після перезапуску"
)


def test_missing_database_url_warns(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "load_env_file", lambda: False)

    with caplog.at_level(logging.WARNING, logger="src.api.main"):
        app = main.create_app()

    assert app.state.database_pool is None
    assert DATABASE_WARNING in caplog.text


def test_database_url_does_not_warn(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://notely@localhost:5432/notely_test"
    )
    monkeypatch.setattr(main, "load_env_file", lambda: False)
    monkeypatch.setattr(
        main, "create_pool", lambda *_args, **_kwargs: object()
    )

    with caplog.at_level(logging.WARNING, logger="src.api.main"):
        app = main.create_app()

    assert app.state.database_pool is not None
    assert DATABASE_WARNING not in caplog.text


# p.s. File was created by Copilot and reviewed by Olha Bidochka
