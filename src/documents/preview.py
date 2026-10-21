"""Прев'ю тексту абзацу для списку документів."""

ELLIPSIS = "…"


def make_preview(text: str, limit: int) -> str:
    """Скорочує текст для прев'ю.

    Текст, не довший за ``limit``, повертається без змін. Довший
    обрізається по останньому цілому слову в межах ``limit`` символів,
    і в кінець додається ``…``.
    """
    if len(text) <= limit:
        return text
    return _cut_at_word_boundary(text, limit) + ELLIPSIS


def _cut_at_word_boundary(text: str, limit: int) -> str:
    """Перші ``limit`` символів тексту без недописаного останнього слова."""
    cut = text[:limit]
    word_is_split = text[limit] != " "
    if word_is_split and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut
