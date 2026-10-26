"""Винятки модуля «Документи».

Модуль не знає про HTTP: перетворення винятку на статус і текст
відповіді (наприклад, 422) робить API-адаптер, як у модулі IAM.
"""

from __future__ import annotations


class DocumentsError(Exception):
    """Базовий виняток модуля «Документи»."""


class ParagraphPositionError(DocumentsError):
    """Позиція абзацу виходить за межі документа."""


# File was created by Claude. Reviewed by Kozynska Anastasia
