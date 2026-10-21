"""Тести make_preview: короткий фрагмент тексту для списку документів."""

from src.documents.preview import make_preview


def test_short_text_is_returned_unchanged() -> None:
    text = "Зустріч у понеділок"
    assert make_preview(text, limit=80) == text


def test_long_text_is_truncated_with_ellipsis() -> None:
    text = "Зустріч у понеділок о десятій, обговорюємо план проєкту"
    assert make_preview(text, limit=19) == "Зустріч у понеділок…"


def test_preview_does_not_cut_words_in_half() -> None:
    text = "Зустріч у понеділок о десятій, обговорюємо план проєкту"
    assert make_preview(text, limit=45) == (
        "Зустріч у понеділок о десятій, обговорюємо…"
    )


def test_single_long_word_is_cut_at_limit() -> None:
    link = "https://github.com/ukma-fin-ssdm-2026/noproblem"
    assert make_preview(link, limit=20) == "https://github.com/u…"
