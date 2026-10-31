# Прогрес реалізації NoteLy (Лабораторна 5, стан оновлено 31.10.2026)

## Підсумок

Таблицю оновлено під код у `main` станом на 31.10.2026. Розділи нижче, від «Мінімального робочого прототипу» до «Рішень з безпеки», описують прототип Лаб 5 і збережені як історія етапу.

| Компонент (Лаб 3) | Стан | Де в коді |
| --- | --- | --- |
| **IAM: автентифікація** | ✅ Працює, покрито тестами, дані в PostgreSQL | `src/iam/service.py`, `src/iam/postgres.py`, `src/api/auth/`, `src/api/security.py` |
| **IAM: ролі Owner / Editor / Guest** (FR-040–FR-043, FR-057) | ✅ Працює, покрито тестами | `src/iam/access.py`, `src/api/access.py` |
| IAM: режим «За посиланням» і запити на доступ (подати, переглянути свої, схвалити, відхилити) | ✅ Працює, покрито тестами | `src/iam/access.py`, `src/api/access.py`, міграція `003_access_requests.sql` |
| IAM: запити на підвищення ролі до Editor, запрошення незареєстрованих користувачів (FR-007) | ⏳ Не реалізовано | — |
| **Документи: створення, перейменування, кошик, відновлення, абзаци** | ✅ Окремий модуль із перевіркою прав, дані в PostgreSQL | `src/documents/`, `src/api/documents.py` |
| **Пошук** за назвою та текстом абзаців з урахуванням прав | ✅ Працює, покрито тестами і Locust-тестом NFR-PERF-005 | `src/search/`, `src/api/search.py` |
| **Календар подій**: події, учасники, прив'язка документа | ✅ Працює, покрито тестами | `src/calendar_events/`, `src/api/calendar.py`, міграція `004_calendar_events.sql` |
| **PostgreSQL** (ADR-002): адаптери портів і SQL-міграції | ✅ Працює; без `DATABASE_URL` застосунок переходить на сховища в пам'яті | `src/db/`, `src/*/postgres.py`, `src/db/migrations/001–004` |
| Шлюз: перевірка токена (I-02) | ✅ Для всіх маршрутів, крім реєстрації та входу | `src/api/security.py` |
| Метрики Prometheus і дашборд Grafana | ✅ Працює | `src/api/metrics.py`, `monitoring/` |
| Шлюз: ліміти запитів за IP | ⏳ Не реалізовано | — |
| Collab (спільне редагування в реальному часі), Scheduler | 🧱 Каркаси пакетів | `src/collab/`, `src/scheduler/` |
| Вебклієнт (інтерфейс користувача) | ⏳ Не реалізовано, робота через REST API і Swagger UI | — |

На момент Лаб 5 робочим компонентом був лише **IAM** (автентифікація й ролі). Зараз наскрізно, від HTTP до PostgreSQL, працюють IAM, документи з кошиком, керування доступом із запитами, пошук і календар.

## Мінімальний робочий прототип (до Лаб 6)

Прототип проходить основний шлях користувача NoteLy через REST API:

1. Олена реєструється, створює документ (стає власницею) і пише абзац.
2. Олена ділиться документом з Андрієм як з редактором — він бачить документ у своєму списку й редагує його.
3. Марко (сторонній) документа не бачить, а за прямим посиланням отримує 403.
4. Олена знижує Андрія до гостя (читати можна, редагувати — ні), а потім забирає доступ зовсім.

Увесь цей шлях автоматично перевіряє тест `tests/api/test_documents_api.py::test_prototype_story`.

**Спробувати вручну** (`uvicorn src.api.main:app --reload --port 3000`, Swagger UI — `http://localhost:3000/api-docs`):
зареєструвати двох користувачів (`POST /auth/register`) → кнопка **Authorize** з токеном першого → `POST /documents` → `PUT /documents/{id}/access` з email другого → **Authorize** з токеном другого → `GET /documents`.

## Структура коду

```
src/
├── api/                  ← FastAPI: компоненти «Шлюз» і «REST API»
│   ├── main.py           create_app(), маршрути документів, підключення IAM
│   ├── common.py         ApiError і спільні описи відповідей з помилками
│   ├── security.py       Шлюз: Bearer-токен → AuthService.verify_session (I-02)
│   ├── access.py         маршрути /documents/{id}/access → AccessService
│   └── auth/             маршрути /api/v1/auth → AuthService (I-05)
│       ├── routes.py     тонкі обробники: HTTP → виклик сервісу → HTTP
│       ├── schemas.py    Pydantic-схеми запитів і відповідей
│       └── errors.py     таблиця «виняток IAM → статус і текст»
├── iam/                  ← модуль IAM, без FastAPI
│   ├── models.py         правила: політики (8 символів, 5 спроб, 15 хв) і сутності
│   ├── errors.py         винятки: що саме пішло не так
│   ├── ports.py          інтерфейси: сховища, хешування, пошта, годинник
│   ├── service.py        AuthService: register, login, logout, verify_session, unlock_account
│   ├── access.py         AccessService: ролі в документах, check(), share(), revoke()
│   ├── adapters.py       реалізації портів: сховища в пам'яті, Argon2id, пошта в журнал, час
│   └── bootstrap.py      build_iam(), build_access(): збирають сервіси з адаптерів
└── documents/ collab/ search/ calendar_events/ scheduler/   ← каркаси
tests/
├── iam/                  правила, сервіс, Argon2, архітектурні правила
└── api/                  HTTP-рівень через TestClient
```

### Чому саме так

1. **Модульний моноліт → пакет на компонент.** Кожен компонент компонентної діаграми має власний пакет у `src/`. Компоненти спілкуються викликами в межах процесу (`high-level-design.md`, розділ 6, п. 7).
2. **Межа між бізнес-логікою та фреймворком** (критерій 4 огляду). FastAPI є лише в `src/api/`. Модуль `src/iam` можна запустити й протестувати без нього, і це автоматично перевіряє `tests/iam/test_architecture.py`.
3. **Порти й адаптери.** `AuthService` отримує сховища, хешування, пошту й годинник через інтерфейси (`ports.py`). Тому тести підставляють швидкі підробки (наприклад, годинник, який можна «перемотати» на 15 хвилин), а перехід на PostgreSQL означатиме лише новий адаптер.
4. **Свідомо проста структура (YAGNI).** Усі сценарії автентифікації зібрано в одному класі `AuthService`, а не розкладено по окремих файлах. Ролі в документах — інша відповідальність («що тобі можна?» замість «хто ти?»), тому вони отримали окремий `AccessService`, а не розширили `service.py`.
5. **Права — одна таблиця.** `ROLE_PERMISSIONS` у `models.py` описує, що може кожна роль; усе, чого там немає, заборонено (default deny). Власник — звичайний запис доступу з роллю `OWNER`, тож IAM лишається єдиним джерелом правди про ролі.

## Простежуваність: вимоги → код → тести

| Вимога | Реалізація | Тести |
| --- | --- | --- |
| FR-001 реєстрація (email, ім'я, пароль ≥ 8) | `AuthService.register`, `PasswordPolicy`, `Email`, `DisplayName` | `TestRegistration`, `TestPasswordPolicy`, `TestEmail` |
| FR-002 конкретна причина відмови | `EmailAlreadyRegisteredError` → 409, `PasswordTooShortError` → 422 з текстом | `test_short_password_gives_specific_message`, `test_taken_email_gives_409` |
| FR-003 вхід і сесія з токеном | `AuthService.login`, `_issue_session` | `TestLogin` |
| FR-004 узагальнене «Невірний email або пароль» | один `InvalidCredentialsError` для всіх причин | `test_any_failure_is_the_same_generic_error`, `test_unknown_email_is_indistinguishable` |
| FR-005 / NFR-SEC-003 блокування 5 спроб / 15 хв, розблокування за листом | `User.with_failed_login`, `LockoutPolicy`, `AuthService.unlock_account` | `TestLockout`, `TestUnlockByEmail`, `test_lockout_gives_423_with_retry_after` |
| FR-006 вихід інвалідує токен ≤ 1 с | `AuthService.logout`: видалення сесії на сервері | `test_logout_invalidates_token_immediately`, `test_logout_then_token_is_rejected` |
| I-02 Шлюз → IAM | `security.py`, `AuthService.verify_session` | `TestProtectedRoutes` |
| I-19 збій пошти не маскується | `_send_unlock_email`: запис `unlock_email_failed` у журнал безпеки | `test_mail_failure_does_not_cancel_lock` |
| Атрибут якості 2.2 (401 + security в OpenAPI) | `HTTPBearer` у `security.py` | `test_openapi_marks_protected_routes` |
| FR-040 надати доступ за email, FR-043 змінити роль | `AccessService.share` | `test_sharing_again_changes_role`, `test_prototype_story` |
| FR-041 Owner/Editor редагують, Guest лише читає | `ROLE_PERMISSIONS`, `AccessService.check` | `test_role_matrix` (усі ролі × усі дії) |
| FR-042 забрати доступ | `AccessService.revoke` | `test_revoke_removes_access` |
| FR-057 / NFR-SEC-004 доступом керує лише власник | дія `MANAGE_ACCESS` лише в Owner | `test_only_owner_can_share` |
| NFR-SEC-001 без прав немає доступу | перевірка прав у кожному маршруті документів, default deny | `test_stranger_is_denied_everything`, `test_missing_and_foreign_documents_look_the_same` |
| FR-014, FR-019, FR-022 перейменування / кошик / відновлення | дії `EDIT` і `TRASH` | `test_only_owner_trashes_and_restores` |

## Рішення з безпеки (для `static-analysis.md` і огляду)

| Загроза (`threat-model.md`) | Контрзахід у коді |
| --- | --- |
| R1 Spoofing: підробка або крадіжка токена | 256-бітні токени з `secrets`; у сховищі лише SHA-256 відбиток; два таймаути сесії (30 хв бездіяльності, 12 год абсолютно); вихід видаляє сесію на сервері; новий токен на кожен вхід (захист від session fixation) |
| R1: підбір пароля | Argon2id; блокування після 5 спроб *атомарне* (тест паралельної атаки: рівно 5 перевірок із 20 потоків) |
| R7 Information disclosure через Mail | у листі лише ім'я та одноразове посилання; токен діє до кінця блокування; розблокування через `POST`, а не `GET` |
| Перелічення акаунтів (user enumeration) | однакова відповідь на неправильний пароль і неіснуючий email; вирівнювання часу фіктивною перевіркою хешу |
| R2 Elevation of privilege | права перевіряє сервер перед кожною дією; не-власник не може змінювати ролі; роль власника не можна змінити чи забрати |
| Перебір чужих документів | 403 і для чужого, і для неіснуючого `id` (права перевіряються до пошуку документа); кожна відмова в журналі `notely.security` |

**Свідомо прийняті ризики** (кандидати в розділ «документована вразливість»):

1. **Перелічення через реєстрацію і 423.** FR-002 вимагає повідомляти «email зайнятий», а діаграма послідовності — повертати 423 для заблокованого акаунта. Обидва розкривають, що email зареєстровано. Ризик прийнято, бо він випливає з вимог; пом'якшення — ліміти запитів за IP на Шлюзі (заплановано).
2. **Блокування як DoS.** Хто знає чужий email, може п'ятьма запитами заблокувати вхід власника на 15 хвилин. Це властивість FR-005; пом'якшення — блокування тимчасове, лист дозволяє розблокувати акаунт одразу.
3. **`LoggingEmailSender` пише посилання розблокування в журнал.** Лише для розробки: під час запуску без SMTP виводиться попередження. Буде замінено SMTP-адаптером.

## Відомі обмеження

Стан на 31.10.2026:

- Сховища в пам'яті лишилися лише для тестів і запуску без `DATABASE_URL`; з базою дані зберігаються в PostgreSQL.
- У `data-model.md` досі немає таблиць `sessions`, `unlock_tokens` та `idempotency_keys`, хоча міграції їх уже створюють.
- Доступ можна надати лише вже зареєстрованому користувачу; запрошення за email для нових користувачів (FR-007) не реалізовано.
- Листи для розблокування не надсилаються: без SMTP `LoggingEmailSender` лише фіксує в журналі, що лист не надіслано.
- Демо-документ з `id=1` прибрано: після захисту маршрутів у нього не було б власника.

## Як запустити

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                   # усі тести
black --check .                          # форматування (як у CI)
flake8 .                                 # стиль (як у CI)
bandit -r src -ll                        # аналізатор безпеки (як у CI)
pip-audit -r requirements.txt            # вразливості залежностей (SCA)
uvicorn src.api.main:app --reload --port 3000
```

Ручна перевірка у Swagger UI (`http://localhost:3000/api-docs`): `POST /auth/register` → скопіювати `access_token` → кнопка **Authorize** → `GET /auth/me`.

## Наступні кроки

Режим «За посиланням», запити на доступ, PostgreSQL, пошук і календар уже реалізовано. Далі:

1. **Доступ, етап 3:** запити на підвищення ролі до Editor і запрошення незареєстрованих користувачів (FR-007).
2. **SMTP:** адаптер `EmailSender` із STARTTLS замість `LoggingEmailSender`.
3. **Collab:** спільне редагування в реальному часі через WebSocket, автозбереження й історія версій.
4. **Шлюз:** ліміти запитів за IP.
5. **Вебклієнт:** інтерфейс користувача поверх наявного REST API.

---
*File was created by Claude. Reviewed by Kozynska Anastasia*
