"""Сервіс автентифікації: усі сценарії IAM в одному класі.

``AuthService`` — це «рецепти»: у якому порядку перевіряти дані,
коли рахувати спробу, коли блокувати акаунт і коли видавати сесію.
Самі правила він бере з ``models.py``, а все зовнішнє (сховища,
хешування, пошту, час) отримує через порти з ``ports.py``.

=====================  ==============================  ================
Метод                  Дія                             Вимоги
=====================  ==============================  ================
``register``           реєстрація + перша сесія        FR-001, FR-002
``login``              вхід, лічильник, блокування     FR-003…FR-005
``logout``             вихід, видалення сесії          FR-006
``verify_session``     «чий це токен?» для Шлюзу       I-02
``unlock_account``     розблокування за листом         FR-005, I-19
=====================  ==============================  ================

"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID, uuid4

from src.iam.errors import (
    AccountLockedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidEmailError,
    InvalidSessionError,
    InvalidUnlockTokenError,
)
from src.iam.models import (
    DisplayName,
    Email,
    LockoutPolicy,
    PasswordPolicy,
    Session,
    SessionPolicy,
    UnlockToken,
    User,
)
from src.iam.ports import (
    Clock,
    EmailDeliveryError,
    EmailMessage,
    EmailSender,
    PasswordHasher,
    SessionRepository,
    TokenGenerator,
    UnlockTokenRepository,
    UserRepository,
)

# Окремий журнал подій безпеки (Project-Description 4.5: спроби
# неавторизованого доступу логуються). Правила запису: ніколи не
# логувати паролі й токени; замість email (персональні дані) — user_id.
security_log = logging.getLogger("notely.security")

# Токени ``SecretsTokenGenerator`` мають 43 символи. Довші рядки
# відкидаються одразу, без хешування.
_MAX_TOKEN_LENGTH = 256


#
# Сервіс повертає назовні:
#


@dataclass(frozen=True)
class UserView:
    """Публічні дані користувача, без хешу пароля і лічильників."""

    id: UUID
    email: str
    name: str
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> UserView:
        return cls(
            id=user.id,
            email=str(user.email),
            name=str(user.name),
            created_at=user.created_at,
        )


@dataclass(frozen=True)
class IssuedSession:
    """Щойно видана сесія.

    Attributes:
        access_token: Токен для заголовка ``Authorization: Bearer``.
            Існує у відкритому вигляді лише тут, щоб передати його
            клієнту один раз; ``repr=False`` не дає йому потрапити в
            журнал.
        expires_at: Абсолютний кінець сесії; через бездіяльність вона
            може закінчитися раніше.
    """

    access_token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class AuthResult:
    """Результат успішної реєстрації або входу."""

    user: UserView
    session: IssuedSession


def hash_token(token: str) -> str:
    """Повертає SHA-256 відбиток токена для зберігання.

    Чому SHA-256, а не Argon2, як для паролів? Пароль придумує людина,
    і його можна підібрати перебором, тож потрібна *повільна* функція.
    Токен — 256 біт випадковості: перебір неможливий за будь-якої
    швидкості хешування, а детермінований результат дозволяє шукати
    сесію за відбитком.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


#
# Сервіс
#


class AuthService:
    """Публічний інтерфейс IAM для інших компонентів (I-02, I-05).

    Екземпляр створює ``bootstrap.build_iam()``.
    """

    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionRepository,
        unlock_tokens: UnlockTokenRepository,
        hasher: PasswordHasher,
        tokens: TokenGenerator,
        email_sender: EmailSender,
        clock: Clock,
        password_policy: PasswordPolicy,
        lockout_policy: LockoutPolicy,
        session_policy: SessionPolicy,
        unlock_page_url: str,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._unlock_tokens = unlock_tokens
        self._hasher = hasher
        self._tokens = tokens
        self._email_sender = email_sender
        self._clock = clock
        self._password_policy = password_policy
        self._lockout_policy = lockout_policy
        self._session_policy = session_policy
        self._unlock_page_url = unlock_page_url
        # Хеш випадкового пароля для вирівнювання часу відповіді (login).
        self._dummy_hash = hasher.hash(secrets.token_urlsafe(16))

    # -- Реєстрація (FR-001, FR-002) ---------------------------------------

    def register(self, email: str, name: str, password: str) -> AuthResult:
        """Створює акаунт і одразу відкриває сесію.

        Сесія відкривається одразу, бо за US-003 після реєстрації
        користувача перенаправляють до робочого простору.

        Порядок перевірок: спершу формат (дешево), потім унікальність
        email, і лише тоді хешування (дорого, ~50 мс).

        Raises:
            InvalidEmailError, InvalidNameError: Некоректні дані.
            PasswordTooShortError, PasswordTooLongError: Пароль не
                відповідає політиці.
            EmailAlreadyRegisteredError: Email уже зайнятий.
        """
        parsed_email = Email.parse(email)
        parsed_name = DisplayName.parse(name)
        self._password_policy.check(password)

        # Швидка перевірка, щоб не хешувати пароль даремно. Остаточну
        # гарантію унікальності дає атомарний ``add`` нижче.
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
        return AuthResult(
            user=UserView.from_user(user), session=self._issue_session(user)
        )

    # -- Вхід (FR-003, FR-004, FR-005) -------------------------------------

    def login(self, email: str, password: str) -> AuthResult:
        """Перевіряє email і пароль та видає сесію.

        Повторює діаграму послідовності ``sequence_diagram.puml``:
        заблоковано → 423; неправильно → лічильник +1 (на 5-й спробі
        блокування й лист) → 401; правильно → сесія.

        Raises:
            InvalidCredentialsError: Невірна пара email/пароль (FR-004).
            AccountLockedError: Вхід тимчасово заблоковано (FR-005).
        """
        user = self._find_user(email)
        if user is None:
            # Захист від атаки за часом: без цієї перевірки відповідь для
            # неіснуючого email приходила б на ~50 мс швидше (без Argon2),
            # і так можна було б дізнатися, які email зареєстровані.
            self._hasher.verify(self._dummy_hash, password)
            security_log.warning("login_failed reason=unknown_account")
            raise InvalidCredentialsError()

        now = self._clock.now()
        if user.is_locked(now):
            security_log.warning("login_rejected_locked user_id=%s", user.id)
            raise AccountLockedError(_locked_until(user), now)

        if self._hasher.verify(user.password_hash, password):
            return self._login_succeeded(user, password, now)
        self._login_failed(user, now)
        raise InvalidCredentialsError()

    def _find_user(self, email: str) -> User | None:
        try:
            return self._users.get_by_email(Email.parse(email))
        except InvalidEmailError:
            return None

    def _login_succeeded(
        self, user: User, password: str, now: datetime
    ) -> AuthResult:
        new_hash = None
        if self._hasher.needs_rehash(user.password_hash):
            new_hash = self._hasher.hash(password)

        def apply(current: User) -> User:
            # Повторна перевірка під атомарним оновленням: паралельні
            # невдалі спроби могли щойно заблокувати акаунт.
            if current.is_locked(now):
                raise AccountLockedError(_locked_until(current), now)
            updated = current.with_lock_cleared()
            if new_hash is not None:
                updated = updated.with_password_hash(new_hash)
            return updated

        updated = self._users.update(user.id, apply)
        if updated is None:
            raise InvalidCredentialsError()
        security_log.info("login_succeeded user_id=%s", updated.id)
        return AuthResult(
            user=UserView.from_user(updated),
            session=self._issue_session(updated),
        )

    def _login_failed(self, user: User, now: datetime) -> None:
        def apply(current: User) -> User:
            if current.is_locked(now):
                raise AccountLockedError(_locked_until(current), now)
            return current.with_failed_login(now, self._lockout_policy)

        updated = self._users.update(user.id, apply)
        if updated is None:
            return
        if updated.is_locked(now):
            # Ця спроба була останньою дозволеною: вона ще отримує 401,
            # а наступні вже 423.
            security_log.warning(
                "account_locked user_id=%s until=%s",
                updated.id,
                _locked_until(updated).isoformat(),
            )
            self._send_unlock_email(updated)
        else:
            security_log.warning(
                "login_failed reason=wrong_password user_id=%s attempts=%d",
                updated.id,
                updated.failed_login_attempts,
            )

    # -- Вихід (FR-006) ----------------------------------------------------

    def logout(self, token: str) -> None:
        """Завершує сесію на сервері.

        Сесія видаляється зі сховища, тож уже наступний запит із цим
        токеном отримає 401 (FR-006: «протягом 1 секунди»). Операція
        ідемпотентна: повторний вихід не є помилкою.
        """
        if self._sessions.delete_by_token_hash(hash_token(token)):
            security_log.info("logout")

    # -- Перевірка токена (I-02: Шлюз → IAM) -------------------------------

    def verify_session(self, token: str) -> UserView:
        """Визначає користувача за токеном і продовжує сесію.

        Відповідає лише на питання «хто це?» (автентифікація). Чи
        можна цьому користувачу працювати з документом
        (авторизація), вирішуватиме перевірка ролей (частина 2).

        Raises:
            InvalidSessionError: Токен невідомий, відкликаний або
                прострочений (бездіяльність чи абсолютний строк).
        """
        if not token or len(token) > _MAX_TOKEN_LENGTH:
            raise InvalidSessionError()
        session = self._sessions.get_by_token_hash(hash_token(token))
        if session is None:
            raise InvalidSessionError()

        now = self._clock.now()
        if session.is_expired(now, self._session_policy):
            self._sessions.delete(session.id)
            raise InvalidSessionError()

        user = self._users.get_by_id(session.user_id)
        if user is None:
            self._sessions.delete(session.id)
            raise InvalidSessionError()

        if session.needs_touch(now, self._session_policy):
            self._sessions.save(session.touched(now))
        return UserView.from_user(user)

    # -- Розблокування за листом (FR-005, I-19) ----------------------------

    def unlock_account(self, token: str) -> None:
        """Знімає блокування за одноразовим токеном із листа.

        Токен видаляється *до* перевірки строку дії (``pop``), тож
        навіть прострочений токен не можна використати повторно.

        Raises:
            InvalidUnlockTokenError: Токен невідомий, використаний або
                прострочений.
        """
        stored = self._unlock_tokens.pop(hash_token(token))
        if stored is None or stored.is_expired(self._clock.now()):
            security_log.warning("unlock_rejected")
            raise InvalidUnlockTokenError()
        updated = self._users.update(
            stored.user_id, lambda user: user.with_lock_cleared()
        )
        if updated is None:
            raise InvalidUnlockTokenError()
        security_log.info("account_unlocked user_id=%s", stored.user_id)

    # -- Пошук користувачів (для доступу до документів, I-13) --------------

    def find_user_by_email(self, email: str) -> UserView | None:
        """Повертає користувача за email або ``None``."""
        try:
            user = self._users.get_by_email(Email.parse(email))
        except InvalidEmailError:
            return None
        return None if user is None else UserView.from_user(user)

    def get_user(self, user_id: UUID) -> UserView | None:
        """Повертає користувача за ідентифікатором або ``None``."""
        user = self._users.get_by_id(user_id)
        return None if user is None else UserView.from_user(user)

    # -- Допоміжні методи --------------------------------------------------

    def _issue_session(self, user: User) -> IssuedSession:
        """Створює нову сесію.

        Кожен вхід отримує *новий* токен. Це захист від фіксації сесії
        (session fixation): токен, відомий зловмиснику до входу, після
        входу недійсний.
        """
        now = self._clock.now()
        token = self._tokens.new_token()
        session = Session(
            id=uuid4(),
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._session_policy.absolute_lifetime,
        )
        self._sessions.add(session)
        return IssuedSession(access_token=token, expires_at=session.expires_at)

    def _send_unlock_email(self, user: User) -> None:
        """Надсилає лист з одноразовим посиланням розблокування.

        Посилання веде на сторінку вебклієнта, яка робить
        ``POST /api/v1/auth/unlock``. Чому не прямий ``GET`` на API:
        розблокування змінює стан, а поштові антивіруси самі
        відкривають ``GET``-посилання й «спалили» б одноразовий токен.

        Збій пошти не скасовує блокування (воно однаково зніметься
        через 15 хвилин). Помилку записуємо в журнал, а не маскуємо
        (I-19).
        """
        locked_until = _locked_until(user)
        token = self._tokens.new_token()
        self._unlock_tokens.add(
            UnlockToken(
                token_hash=hash_token(token),
                user_id=user.id,
                expires_at=locked_until,
            )
        )
        link = f"{self._unlock_page_url}?{urlencode({'token': token})}"
        message = EmailMessage(
            recipient=str(user.email),
            subject="NoteLy: вхід до акаунта тимчасово заблоковано",
            body=(
                f"Вітаємо, {user.name}!\n\n"
                "Ми зафіксували кілька невдалих спроб увійти до вашого "
                "акаунта, тому тимчасово заблокували вхід.\n"
                "Блокування зніметься автоматично. Щоб розблокувати "
                f"акаунт одразу, перейдіть за посиланням:\n{link}\n\n"
                "Якщо це були не ви, радимо змінити пароль."
            ),
        )
        try:
            self._email_sender.send(message)
        except EmailDeliveryError:
            security_log.error(
                "unlock_email_failed user_id=%s", user.id, exc_info=True
            )


def _locked_until(user: User) -> datetime:
    # ``is_locked`` гарантує, що поле заповнене; перевірка потрібна для
    # аналізатора типів і на випадок помилки виклику.
    if user.locked_until is None:
        raise ValueError("Користувач не заблокований.")
    return user.locked_until


# File was created by Claude. Reviewed by Kozynska Anastasia
