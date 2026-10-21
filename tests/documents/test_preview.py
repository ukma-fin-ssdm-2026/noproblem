"""Тести make_preview: короткий фрагмент тексту для списку документів."""

from src.documents.preview import make_preview


def test_short_text_is_returned_unchanged() -> None:
    text = "Зустріч у понеділок"
    assert make_preview(text, limit=80) == text
