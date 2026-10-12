# Прогрес реалізації NoteLy (Лабораторна 5)

## Підсумок

| Компонент (Лаб 3) | Стан | Де в коді |
| --- | --- | --- |
| **IAM: автентифікація** | ✅ Працює, покрито тестами | `src/iam/`, `src/api/auth/`, `src/api/security.py` |
| IAM: ролі та керування доступом (FR-040–FR-057) | ⏳ Частина 2 | `src/iam/application/access_control/` (план) |
| REST API: документи, кошик, абзаци | ✅ Демо з Лаб 4 (у пам'яті) | `src/api/main.py` |
| Шлюз: перевірка токена (I-02) | ✅ Для маршрутів `/auth` | `src/api/security.py` |
| Шлюз: ліміти запитів за IP | ⏳ Заплановано | — |
| Docs, Collab, Search, Calendar, Scheduler | 🧱 Каркас пакетів з описом інтерфейсів | `src/documents/`, `src/collab/`, `src/search/`, `src/calendar_events/`, `src/scheduler/` |
| PostgreSQL (ADR-002) | ⏳ Частина 3: адаптери тих самих портів | — |

Компонент, що «працює й відповідає стандартам якості цієї лабораторної» — **IAM (автентифікація)**.

## Структура коду

```
src/
├── api/                     ← FastAPI: компоненти «Шлюз» і «REST API»
│   ├── main.py              create_app(), маршрути документів, підключення IAM
│   ├── common.py            ApiError і спільні описи відповідей
│   ├── security.py          Шлюз: Bearer-токен → IamModule.verify_session (I-02)
│   └── auth/                маршрути /api/v1/auth → IamModule (I-05)
│       ├── routes.py        тонкі обробники: HTTP → виклик IAM → HTTP
│       ├── schemas.py       Pydantic-схеми запитів/відповідей
│       └── errors.py        таблиця «доменний виняток → статус і текст»
├── iam/                     ← модуль IAM, БЕЗ FastAPI
│   ├── domain/              сутності (User, Session, UnlockToken), політики, винятки
│   ├── application/
│   │   ├── ports.py         інтерфейси: сховища, хешування, пошта, годинник
│   │   ├── dto.py           UserView, AuthResult — що IAM віддає назовні
│   │   ├── audit.py         журнал безпеки notely.security
│   │   └── authentication/  register.py, login.py, logout.py, verify_session.py, unlock.py
│   ├── infrastructure/      in-memory сховища, Argon2id, «пошта в журнал», годинник
│   ├── module.py            фасад IamModule — публічний інтерфейс для інших модулів
│   └── bootstrap.py         composition root: build_iam()
└── documents/ collab/ search/ calendar_events/ scheduler/   ← каркаси
tests/
├── iam/                     домен, сценарії, Argon2, архітектурні правила
└── api/                     HTTP-рівень через TestClient
```

### Чому саме так

1. **Модульний моноліт → пакет на компонент.** Кожен компонент компонентної діаграми має власний пакет у `src/`. Компоненти спілкуються викликами в межах процесу через фасад (`IamModule`), як описано в `high-level-design.md` (розділ 6, п. 7).
2. **Порти й адаптери всередині модуля** (критерій 4 огляду: межа між бізнес-логікою та фреймворком). Залежності спрямовані лише всередину: `infrastructure → application → domain`. FastAPI живе тільки в `src/api/`, і це автоматично перевіряє `tests/iam/test_architecture.py`.
3. **Один сценарій = один файл.** Кожен файл в `application/authentication/` відповідає конкретній групі вимог, тож простежуваність «вимога → код → тест» видно зі структури папок.
4. **Тонкий адаптер.** Обробник маршруту робить три кроки: розібрати запит, викликати `IamModule`, побудувати відповідь. Його можна замінити на WebSocket чи CLI, не чіпаючи логіку.

## Простежуваність: вимоги → код → тести

| Вимога | Реалізація | Тести |
| --- | --- | --- |
| FR-001 реєстрація (email, ім'я, пароль ≥ 8) | `register.py`, `PasswordPolicy`, `Email`, `DisplayName` | `TestRegistration`, `TestPasswordPolicy`, `TestEmail` |
| FR-002 конкретна причина відмови | `EmailAlreadyRegisteredError` → 409, `PasswordTooShortError` → 422 з текстом | `test_short_password_gives_specific_message`, `test_taken_email_gives_409` |
| FR-003 вхід і сесія з токеном | `login.py`, `sessions.py` | `TestLogin` |
| FR-004 узагальнене «Невірний email або пароль» | один `InvalidCredentialsError` для всіх причин | `test_any_failure_is_the_same_generic_error`, `test_unknown_email_is_indistinguishable` |
| FR-005 / NFR-SEC-003 блокування 5 спроб / 15 хв, розблокування за листом | `User.with_failed_login`, `LockoutPolicy`, `unlock.py` | `TestLockout`, `TestUnlockByEmail`, `test_lockout_gives_423_with_retry_after` |
| FR-006 вихід інвалідує токен ≤ 1 с | `logout.py`: видалення сесії на сервері | `test_logout_invalidates_token_immediately`, `test_logout_then_token_is_rejected` |
| I-02 Шлюз → IAM | `security.py`, `verify_session.py` | `TestProtectedRoutes` |
| I-19 збій пошти не маскується | `UnlockNotifier`: журнал `unlock_email_failed` | `test_mail_failure_does_not_cancel_lock` |
| Атрибут якості 2.2 (401 + security у OpenAPI) | `HTTPBearer` у `security.py` | `test_openapi_marks_protected_routes` |

## Рішення з безпеки (для `static-analysis.md` і огляду)

| Загроза (threat-model.md) | Контрзахід у коді |
| --- | --- |
| R1 Spoofing: підробка або крадіжка токена | 256-бітні токени з `secrets`; у сховищі лише SHA-256 відбиток; два таймаути сесії (30 хв бездіяльності / 12 год); вихід видаляє сесію на сервері; новий токен на кожен вхід (захист від session fixation) |
| R1: підбір пароля | Argon2id; блокування після 5 спроб *атомарне* (тест паралельної атаки: рівно 5 перевірок із 20 потоків) |
| R7 Information disclosure через Mail | у листі лише ім'я та одноразове посилання; токен діє до кінця блокування; розблокування через `POST`, а не `GET` |
| Перелічення акаунтів (user enumeration) | однакова відповідь на неправильний пароль і неіснуючий email; вирівнювання часу фіктивною перевіркою хешу |

**Свідомо прийняті ризики** (кандидати в розділ «документована вразливість»):

1. **Перелічення через реєстрацію і 423.** FR-002 вимагає повідомити «email зайнятий», а діаграма послідовності — повертати 423 для заблокованого акаунта. Обидва розкривають, що email зареєстровано. Ризик прийнято, бо він випливає з вимог. Пом'якшення: ліміти запитів за IP на Шлюзі (заплановано).
2. **Блокування як DoS.** Зловмисник, що знає email, може п'ятьма запитами заблокувати чужий вхід на 15 хвилин. Це властивість FR-005. Пом'якшення: блокування тимчасове, лист дозволяє розблокувати акаунт одразу.
3. **`LoggingEmailSender` пише посилання розблокування в журнал.** Лише для розробки: під час запуску без SMTP виводиться попередження. Буде замінено SMTP-адаптером.

## Відомі обмеження

- Дані в пам'яті: після перезапуску користувачі й сесії зникають (так само, як документи в `main.py`).
- У `data-model.md` немає сутностей `Session` та `UnlockToken`. Їх потрібно додати перед реалізацією PostgreSQL.
- Маршрути документів поки не вимагають токена: без ролей (частина 2) захист дав би лише «будь-який автентифікований користувач бачить усе».
- `src/api/main.py` (з Лаб 4) не відформатовано під black і 79 символів; правило бойскаута застосовуємо під час наступного змістовного редагування файлу.

## Як запустити

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                   # усі тести
flake8 src/iam src/api/auth src/api/security.py src/api/common.py tests
black --check src/iam src/api/auth src/api/security.py src/api/common.py tests
bandit -r src -c pyproject.toml          # аналізатор безпеки
pip-audit -r requirements.txt            # вразливості залежностей (SCA)
uvicorn src.api.main:app --reload --port 3000
```

Ручна перевірка у Swagger UI (`http://localhost:3000/api-docs`): `POST /auth/register` → скопіювати `access_token` → кнопка **Authorize** → `GET /auth/me`.

## Наступні кроки

1. **Частина 2 — керування доступом:** `DocumentAccess`, `AccessRequest`, ролі Owner/Editor/Guest, `IamModule.check_permission()` для I-09/I-11/I-12/I-13, захист маршрутів документів (403).
2. **Частина 3 — PostgreSQL і SMTP:** адаптери тих самих портів (SQLAlchemy + міграції), `SELECT … FOR UPDATE` в `update()`, SMTP із STARTTLS.
3. Додати `flake8`, `black --check`, `bandit`, `pytest` у `.github/workflows/ci.yml` (зараз там «Hello World»).

---
*File was created by Claude (AI-assisted); review by a team member pending.*
