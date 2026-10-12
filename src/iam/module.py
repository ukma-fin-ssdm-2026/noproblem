"""Фасад модуля IAM — єдина точка входу для інших компонентів.

Архітектура (``docs/architecture/high-level-design.md``) описує
модульний моноліт: компоненти викликають одне одного всередині
процесу через внутрішні інтерфейси. Для IAM цей інтерфейс — клас
``IamModule``. REST API (I-05) і Шлюз (I-02) звертаються лише до
нього, а не до окремих сценаріїв чи сховищ. Тож внутрішню будову IAM
можна змінювати, не чіпаючи викликачів.

У частині 2 сюди додадуться методи перевірки прав (I-09, I-11–I-13).
"""

from __future__ import annotations

from src.iam.application.authentication.login import LoginUser
from src.iam.application.authentication.logout import LogoutUser
from src.iam.application.authentication.register import RegisterUser
from src.iam.application.authentication.unlock import UnlockAccount
from src.iam.application.authentication.verify_session import VerifySession
from src.iam.application.dto import AuthResult, UserView


class IamModule:
    """Публічний інтерфейс модуля IAM.

    Екземпляр збирається в ``src/iam/bootstrap.py`` (composition root).
    Опис винятків кожного методу — у відповідному сценарії.
    """

    def __init__(
        self,
        register: RegisterUser,
        login: LoginUser,
        logout: LogoutUser,
        verify_session: VerifySession,
        unlock: UnlockAccount,
    ) -> None:
        self._register = register
        self._login = login
        self._logout = logout
        self._verify_session = verify_session
        self._unlock = unlock

    def register(self, email: str, name: str, password: str) -> AuthResult:
        """Реєструє користувача та відкриває сесію (FR-001, FR-002)."""
        return self._register.execute(email, name, password)

    def login(self, email: str, password: str) -> AuthResult:
        """Виконує вхід (FR-003–FR-005)."""
        return self._login.execute(email, password)

    def logout(self, token: str) -> None:
        """Завершує сесію (FR-006)."""
        self._logout.execute(token)

    def verify_session(self, token: str) -> UserView:
        """Визначає користувача за токеном (I-02)."""
        return self._verify_session.execute(token)

    def unlock_account(self, token: str) -> None:
        """Знімає блокування за посиланням із листа (FR-005)."""
        self._unlock.execute(token)


# File was created by Claude (AI-assisted); review by a team member pending.
