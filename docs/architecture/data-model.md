# Модель даних NoteLy
## 1. Обрана модель
Для NoteLy використано ER-модель, оскільки дані системи мають реляційну структуру та зберігаються у базі даних.

**Модель покриває дані для таких ключових функцій:**
1. Реєстрація, автентифікація та блокування акаунтів (FR-001–FR-007).
2. Створення та керування документами (FR-008–FR-017).
3. Кошик та відновлення документів (FR-018–FR-023).
4. Автозбереження та історія версій (FR-027–FR-032).
5. Розмежування доступу та ролей (FR-040–FR-057).
6. Пошук документів (FR-058–FR-062).
7. Календар і події (FR-063–FR-073).

**[Діаграма](./docs/architecture/uml/data-model.puml)**

## 2. Сутності та атрибути
**User**
* id — PK
* email — персональні дані
* password_hash — чутливі дані
* name — персональні дані
* created_at
* failed_login_attempts
* locked_until

**Document**
* id — PK
* owner_id — FK → User
* title
* content — чутливі дані
* access_mode
* is_deleted
* deleted_at
* created_at
* updated_at

**DocumentAccess**
* id — PK
* document_id — FK → Document
* user_id — FK → User
* role
* created_at

**AccessRequest**
* id — PK
* document_id — FK → Document
* user_id — FK → User
* requested_role
* status
* created_at
  
**DocumentVersion**
* id — PK
* document_id — FK → Document
* author_id — FK → User
* content_snapshot — чутливі дані
* created_at
  
**CalendarEvent**
* id — PK
* creator_id — FK → User
* document_id — FK → Document
* title
* start_time
* end_time
* created_at
  
**EventParticipant**
* id — PK
* event_id — FK → CalendarEvent
* user_id — FK → User
* created_at

## 3. Зв'язки та кардинальність
* User 1 — N Document — користувач є власником документів.
* User 1 — N DocumentAccess — користувач може мати доступ до багатьох документів.
* Document 1 — N DocumentAccess — документ може мати доступ для багатьох користувачів.
* Document 1 — N AccessRequest — документ може мати багато запитів на доступ.
* User 1 — N AccessRequest — користувач може створювати запити на доступ.
* Document 1 — N DocumentVersion — документ має історію версій.
* User 1 — N CalendarEvent — користувач створює події.
* Document 0..1 — N CalendarEvent — документ може бути прив'язаний до подій.
* CalendarEvent 1 — N EventParticipant — подія має учасників.
* User 1 — N EventParticipant — користувач може бути учасником багатьох подій.
## 4. Персональні та чутливі дані
**Персональні:**
* User.email
* User.name
  
**Чутливі:**
* User.password_hash
* Document.content
* DocumentVersion.content_snapshot
* дані про права доступу та участь користувачів у документах і подіях.
