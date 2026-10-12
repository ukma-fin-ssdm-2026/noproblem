"""Відправлення листів (інтерфейс I-19).

Зараз є лише адаптер для розробки, який пише лист у журнал. SMTP-адаптер
(``smtplib`` + STARTTLS, порт 587, як на діаграмі розгортання) буде
додано в частині 3 разом із конфігурацією облікових даних.
"""

from __future__ import annotations

import logging

from src.iam.application.ports import EmailMessage

logger = logging.getLogger("notely.email")


class LoggingEmailSender:
    """Реалізує ``EmailSender``: «надсилає» лист у журнал застосунку.

    ЛИШЕ ДЛЯ РОЗРОБКИ. Тіло листа містить одноразове посилання
    розблокування, а секрети в журналі в робочому середовищі
    неприпустимі. Тому ``bootstrap.py`` вмикає цей адаптер лише тоді,
    коли SMTP не налаштовано, і попереджає про це під час запуску.
    """

    def send(self, message: EmailMessage) -> None:
        # WARNING, а не INFO: лист фактично НЕ надіслано, і про це
        # треба знати. До того ж без налаштування logging рівень INFO
        # не видно в консолі uvicorn, тож посилання загубилося б.
        logger.warning(
            "DEV EMAIL (лист не надіслано, SMTP не налаштовано) "
            "to=%s subject=%s\n%s",
            message.recipient,
            message.subject,
            message.body,
        )


# File was created by Claude (AI-assisted); review by a team member pending.
