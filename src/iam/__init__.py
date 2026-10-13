"""Модуль «Ідентичність і доступ» (IAM) системи NoteLy.

Відповідальність (``docs/architecture/high-level-design.md``):
акаунти, автентифікація, сесії, ролі, запрошення та перевірки доступу.

Будова модуля::

    iam/
    ├── models.py     правила: політики й сутності (чистий Python)
    ├── errors.py     винятки: що саме пішло не так
    ├── ports.py      інтерфейси: що IAM потрібно від зовнішнього світу
    ├── service.py    AuthService: сценарії (реєстрація, вхід, вихід…)
    ├── access.py     AccessService: ролі в документах і перевірка прав
    ├── adapters.py   реалізації портів: сховища, Argon2, пошта, час
    └── bootstrap.py  build_iam(): збирає сервіс з адаптерів

Модуль не залежить від FastAPI: HTTP-адаптер лежить у ``src/api/``
(компонент REST API). Інші компоненти імпортують лише те, що
експортовано тут.
"""

from src.iam.access import AccessService, Member
from src.iam.bootstrap import IamSettings, build_access, build_iam
from src.iam.models import Action, Role
from src.iam.service import AuthResult, AuthService, IssuedSession, UserView

__all__ = [
    "AccessService",
    "Action",
    "AuthResult",
    "AuthService",
    "IamSettings",
    "IssuedSession",
    "Member",
    "Role",
    "UserView",
    "build_access",
    "build_iam",
]

# File was created by Claude. Reviewed by Kozynska Anastasia
