[![CI Test](https://github.com/ukma-fin-ssdm-2026/noproblem/actions/workflows/ci.yml/badge.svg)](https://github.com/ukma-fin-ssdm-2026/noproblem/actions/workflows/ci.yml)

# Проєкт "NoteLy" - застосунок для спільного ведення нотаток

Застосунок для створення, редагування та спільного використання документів у реальному часі. Він підходить як для індивідуального ведення нотаток, так і для командної роботи.

### Основні функції
* редагування у реальному часі групових документів
* зберігання історії версій
* базові можливості форматування
* можливість організовувати свій робочий простір

# Список документації:

1. **[Повний опис проєкту](./Project-Description.md)**

2. **[Статут проєкту](./TeamCharter.md)**

## Артефакти вимог

1. **[Користувацькі історії](./docs/requirements/user-stories.md)**

2. **[Документ з вимогами до систем](./docs/requirements/requirements.md)**

3. **[Матриця простежуваності](./docs/requirements/rtm.md)**

4. **[Міні-ТЗ](./Project-Description.md#4-міні-тз)**

## Архітектура проєкту

1. **[Матриця архітектурної простежуваності](./docs/architecture/traceability-matrix.md)**

2. **[Модель даних NoteLy](./docs/architecture/data-model.md)**

3. **[STRIDE-модель загроз NoteLy](./docs/architecture/threat-model.md)**

*Рішення що до системи:*
 - **[Стратегія розв'язання конфліктів одночасного редагування](./docs/architecture/decisions/ADR-001-conflict-resolution.md)**
 - **[Вибір бази даних](./docs/architecture/decisions/ADR-002-database-choice.md)**
 - **[Архітектурний стиль — клієнт-серверна архітектура з WebSocket](./docs/architecture/decisions/ADR-003-architecture-style.md)**

*UML Архітектури:*
- **[Компонентна діаграма](./docs/architecture/uml/component_diagram.puml)**
- **[Діаграма послідовності](./docs/architecture/uml/sequence_diagram.puml)**
- **[Діаграма розгортання](./docs/architecture/uml/deployment_diagram.puml)**
- **[ER-модель](./docs/architecture/uml/data-model.puml)**

## NoteLy API

![API Docs CI](https://github.com/ukma-fin-ssdm-2026/noproblem/actions/workflows/deploy-api-docs.yml/badge.svg)

Демонстраційний API для документів, кошика й абзаців NoteLy (FastAPI, дані в пам'яті).

**Документація (GitHub Pages):** https://ukma-fin-ssdm-2026.github.io/noproblem/

## Вимоги

- Python 3.10 або новіший (у CI використовується 3.12)

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 3000
```

Swagger UI: http://localhost:3000/api-docs

## База даних (PostgreSQL)

Без змінної `DATABASE_URL` застосунок працює зі сховищами в пам'яті: дані зникають після перезапуску. Якщо `DATABASE_URL` задано, IAM зберігає користувачів, сесії, токени розблокування та ролі доступу в PostgreSQL, а календар — події й учасників; документи поки залишаються в пам'яті. Для роботи з PostgreSQL (ADR-002) у кожного розробника своя локальна база в Docker; спільна між нами лише схема — SQL-міграції в git.

**Налаштування (один раз):**

1. Встановіть [Docker Desktop](https://www.docker.com/products/docker-desktop/) і запустіть його.
2. Встановіть залежності та створіть файл `.env` з випадковим паролем (працює на macOS, Linux і Windows; файл у `.gitignore`):

```bash
pip install -r requirements-dev.txt
python scripts/create_env.py
```

3. Запустіть базу, застосуйте міграції й перевірте тести:

```bash
docker compose up -d                 # PostgreSQL 16 у контейнері
docker compose ps                    # статус має бути "healthy"
python -m src.db.migrate             # створює й оновлює таблиці
pytest
```

Змінні з `.env` підвантажуються автоматично (`python-dotenv`), окремо задавати їх у терміналі не потрібно.

**Дві бази в одному контейнері:**

- `notely` (`DATABASE_URL`) — робоча база для запуску застосунку;
- `notely_test` (`TEST_DATABASE_URL`) — лише для тестів. Тести очищають усі таблиці після кожного тесту, тому працюють тільки з базою, назва якої закінчується на `_test`. Без `TEST_DATABASE_URL` тести бази пропускаються (skipped).

**Щодня:** запущений Docker Desktop і `docker compose up -d`; після `git pull` з новими міграціями — `python -m src.db.migrate`.

**Міграції.** Схема описана SQL-файлами в [`src/db/migrations/`](./src/db/migrations/). Застосований файл не редагують — для змін додають новий із наступним номером. Номери закріплені за модулями: `001` IAM, `002` документи, `003` запити на доступ, `004` календар; далі — наступний вільний.

**Скидання бази.** `docker compose down` зупиняє базу (дані зберігаються), `docker compose down -v` стирає всі дані. Пароль і базу `notely_test` Docker створює лише під час першого запуску з порожнім томом: якщо змінили пароль (`python scripts/create_env.py --force`), виконайте `docker compose down -v`, а потім `docker compose up -d`.

**Якщо «password authentication failed».** Змінні, задані в терміналі, важливіші за `.env` (так і в CI). Якщо раніше ви виконували `source .env` або змінили пароль, у терміналі можуть лишитися старі значення: відкрийте новий термінал (або `unset POSTGRES_PASSWORD DATABASE_URL TEST_DATABASE_URL`) і перестворіть базу: `docker compose down -v && docker compose up -d`.

**CI.** У CI база одноразова й містить лише тестові дані, тому підключення йде без пароля (`POSTGRES_HOST_AUTH_METHOD: trust` у `ci.yml`).

## Генерація OpenAPI-специфікації

Специфікація генерується з анотацій у коді (Code-First) під час запуску сервера; вручну її не редагують. Для ручного оновлення або CI використовуйте ту саму функцію експорту:

```bash
PYTHONPATH=. python scripts/generate_openapi.py
```

Результат: `docs/api/openapi-generated.yaml`. Після змін у `src/api/` запускайте скрипт і комітьте оновлений YAML, інакше перевірка в CI не пройде.

## Публікація документації

Після push у `main` GitHub Actions (`.github/workflows/deploy-api-docs.yml`) встановлює залежності, генерує специфікацію, перевіряє, що закомічений YAML актуальний, і публікує папку `docs/api` на GitHub Pages.

## Тести та перевірки якості

```bash
pip install -r requirements-dev.txt
pytest --cov --cov-report=term-missing
```

Тести запускаються в GitHub Actions для кожного push і pull request.
CI також перевіряє поріг покриття 90%, налаштований у `pyproject.toml`.

### Залежності та lock-файли

Прямі залежності з точними версіями — у `requirements.txt` і `requirements-dev.txt`. CI встановлює їх не звідти, а з lock-файлів `requirements.lock` і `requirements-dev.lock`: там зафіксовано версії **всіх** пакетів, включно з транзитивними, і їхні хеші (`pip install --require-hashes --only-binary=:all:`). Так збірка повторювана, а підмінений пакет або виконання `setup.py` на раннері неможливі.

Після зміни будь-якого `requirements*.txt` перегенеруйте обидва lock-файли й закомітьте їх разом:

```bash
pip install uv
uv pip compile requirements.txt --universal --python-version 3.12 --generate-hashes -o requirements.lock
uv pip compile requirements-dev.txt --universal --python-version 3.12 --generate-hashes -o requirements-dev.lock
```

Інструменти, стан реалізації та структура коду описані в **[прогресі реалізації](./docs/code-quality/progress.md)**.

Перелік граничних випадків, які перевіряють тести: **[граничні випадки](./docs/testing/edge-cases.md)**.

Стратегія розвитку тестування, рівні перевірок і плани CI/CD: **[стратегія тестування](./docs/testing/testing-strategy.md)**.

Покриття тестами та пропозиції щодо якості: **[звіт про тестування](./docs/testing/test-report.md)**, HTML-звіт покриття — у [`htmlcov/`](./htmlcov/index.html).

## Документи

- [Прогрес реалізації (Лаб 5)](./docs/code-quality/progress.md)
- [Проєктування API](./docs/api/api-design.md)
- [Атрибути якості](./docs/api/quality-attributes.md)
- [Специфікація OpenAPI](./docs/api/openapi-generated.yaml)


### Склад команди

1. **Карнаух Дарія**(d.karnaukh@ukma.edu.ua)  ***(на момент 28.10.2026 не приймає учасні у проєкті)*** : Супроводжувач репозиторію, Керівник моделі даних і загроз, Integration Lead

2. **Козинська Анастасія** (a.kozynska@ukma.edu.ua): Супроводжувач CI, Керівник вимог, Керівник функціональних вимог, Керівник архітектури, Backend Lead, API Design Lead, Керівник прототипу, Керівник тестування, Керівник тестових дублерів, Планувальник тестів(+), Відповідальний за документацію(+)

3. **Марущенко Ольга** (o.marushchenko@ukma.edu.ua): Керівник документації, Керівник опису проєкту, Керівник UML, Рецензент коду, Керівник налагодження, Стратег тестування, Аналітик якості(+), Менеджер оглядів(+)

4. **Бідочка Ольга** (o.bidochka@ukma.edu.ua): Керівник трекера завдань, Керівник простежуваності, Quality Lead, Аналітик безпеки, Керівник інтеграції, Рецензент ШІ-коду(+)

Розташування посилань на Loom будуть у папці **[Labs](./Labs)**

**PS: document was partially redacted by Olha Marushchenko**
