"""Сценарій «Реєстрація» (FR-001, FR-002, US-003)."""

from __future__ import annotations

from uuid import uuid4

from src.iam.application.audit import security_log
from src.iam.application.authentication.sessions import SessionIssuer
from src.iam.application.dto import AuthResult, UserView
from src.iam.application.ports import Clock, PasswordHasher, UserRepository
from src.iam.domain.errors import EmailAlreadyRegisteredError
from src.iam.domain.models import DisplayName, Email, User
from src.iam.domain.policies import PasswordPolicy


class RegisterUser:
    """Створює обліковий запис і одразу відкриває сесію.

    Сесія створюється одразу, бо за US-003 після реєстрації
    користувача перенаправляють до робочого простору, а за FR-007
    запрошений користувач після реєстрації має одразу відкрити
    документ. Окремий крок входу тут зайвий.
    """

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        session_issuer: SessionIssuer,
        clock: Clock,
        password_policy: PasswordPolicy,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._session_issuer = session_issuer
        self._clock = clock
        self._password_policy = password_policy

    def execute(self, email: str, name: str, password: str) -> AuthResult:
        """Реєструє користувача.

        Порядок перевірок: спершу формат даних (дешево), потім
        унікальність email, і лише тоді хешування (дорого, близько
        50 мс). Так невалідні запити не навантажують процесор.

        Args:
            email: Email у тому вигляді, як його ввів користувач.
            name: Ім'я для відображення.
            password: Пароль у відкритому вигляді. Ніде не зберігається.

        Returns:
            Дані нового користувача та токен сесії.

        Raises:
            InvalidEmailError: Некоректний формат email.
            InvalidNameError: Порожнє або задовге ім'я.
            PasswordTooShortError: Пароль коротший за 8 символів.
            PasswordTooLongError: Пароль задовгий.
            EmailAlreadyRegisteredError: Email уже зайнятий.
        """
        parsed_email = Email.parse(email)
        parsed_name = DisplayName.parse(name)
        self._password_policy.check(password)

        # Швидка попередня перевірка, щоб не хешувати пароль даремно.
        # Остаточну гарантію унікальності дає атомарний ``add`` нижче.
        if self._users.get_by_email(parsed_email) is not None:
            raise EmailAlreadyRegisteredError(str(parsed_email))

        user = User(
            id=uuid4(),
            email=parsed_email,
            name=parsed_name,
            password_hash=self._hasher.hash(password),
            created_at=self._clock.now(),
        )
        self._users.add(user)
        security_log.info("user_registered user_id=%s", user.id)

        session = self._session_issuer.issue(user.id)
        return AuthResult(user=UserView.from_user(user), session=session)


# File was created by Claude (AI-assisted); review by a team member pending.
