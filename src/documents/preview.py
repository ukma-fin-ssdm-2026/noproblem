"""Прев'ю тексту абзацу для списку документів."""


def make_preview(text: str, limit: int) -> str:
    if len(text) > limit:
        return text[:limit] + "…"
    return text
