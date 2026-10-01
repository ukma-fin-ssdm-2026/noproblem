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

---
### Склад команди

1. **Карнаух Дарія** (d.karnaukh@ukma.edu.ua): Супроводжувач репозиторію, Керівник якості, Керівник моделі даних і загроз (+)

2. **Козинська Анастасія** (a.kozynska@ukma.edu.ua): Супроводжувач CI, Керівник вимог, Керівник функціональних вимог, Керівник архітектури (+)

3. **Марущенко Ольга** (o.marushchenko@ukma.edu.ua): Керівник документації, Керівник опису проєкту, Керівник UML (+)

4. **Бідочка Ольга** (o.bidochka@ukma.edu.ua): Керівник трекера завдань, Керівник простежуваності

Розташування посилань на Loom будуть у папці **[Labs](./Labs)**

**PS: document was partially redacted by Olha Marushchenko**
