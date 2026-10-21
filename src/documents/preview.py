"""Прев'ю тексту абзацу для списку документів."""

ELLIPSIS = "…"


def make_preview(text: str, limit: int) -> str:
    """Скорочує текст для прев'ю.

    Текст, не довший за ``limit``, повертається без змін; довший
    обрізається до ``limit`` символів, і в кінець додається ``…``.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + ELLIPSIS
