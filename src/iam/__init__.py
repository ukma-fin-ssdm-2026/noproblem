"""Модуль «Ідентичність і доступ» (IAM) системи NoteLy.

Відповідальність (``docs/architecture/high-level-design.md``):
акаунти, автентифікація, сесії, ролі, запрошення та перевірки доступу.
IAM — єдине джерело правди про ролі.

Структура (порти й адаптери)::

    iam/
    ├── domain/          правила: сутності, політики, винятки
    ├── application/     сценарії (use cases) і порти-інтерфейси
    ├── infrastructure/  адаптери: сховища, Argon2, пошта, час
    ├── module.py        фасад IamModule (публічний інтерфейс)
    └── bootstrap.py     збирання модуля з адаптерів

Залежності спрямовані лише всередину:
``infrastructure → application → domain``. Модуль не залежить від
FastAPI: HTTP-адаптер лежить у ``src/api/`` (компонент REST API).

Інші компоненти імпортують лише те, що експортовано тут.
"""

from src.iam.application.dto import AuthResult, IssuedSession, UserView
from src.iam.bootstrap import IamSettings, build_iam
from src.iam.module import IamModule

__all__ = [
    "AuthResult",
    "IamModule",
    "IamSettings",
    "IssuedSession",
    "UserView",
    "build_iam",
]
