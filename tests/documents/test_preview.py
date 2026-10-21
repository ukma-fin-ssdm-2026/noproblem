"""Тести make_preview: короткий фрагмент тексту для списку документів."""

import pytest

from src.documents.preview import make_preview

NOTE = "Зустріч у понеділок о десятій, обговорюємо план проєкту"
LINK = "https://github.com/ukma-fin-ssdm-2026/noproblem"


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("Зустріч у понеділок", 80, "Зустріч у понеділок"),
        (NOTE, 19, "Зустріч у понеділок…"),
        (NOTE, 45, "Зустріч у понеділок о десятій, обговорюємо…"),
        (LINK, 20, "https://github.com/u…"),
    ],
    ids=[
        "short-text-is-unchanged",
        "long-text-is-truncated-with-ellipsis",
        "words-are-not-cut-in-half",
        "single-long-word-is-cut-at-limit",
    ],
)
def test_make_preview(text: str, limit: int, expected: str) -> None:
    assert make_preview(text, limit=limit) == expected
