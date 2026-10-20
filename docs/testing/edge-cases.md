# Перелік покритих граничних випадків

Документ описує, які граничні значення й нетипові ситуації перевіряє
набір тестів у `tests/`, і де саме. Для кожної межі тести беруть
значення **на межі** та **одразу за нею** (аналіз граничних значень):
саме там найчастіше трапляються помилки «на одиницю».

Позначення в колонці «Тест»: шлях відносно `tests/`, далі `::` і назва
тестової функції. Якщо тест параметризований, у колонці «Значення»
перелічено всі його випадки.

## 1. Облікові дані та профіль (`src/iam/models.py`)

| Межа | Значення в тестах | Очікування | Тест |
|---|---|---|---|
| Мінімальна довжина пароля — 8 (FR-001) | 7 / 8 символів | відмова / дозволено | `iam/test_models.py::TestPasswordPolicy::test_seven_characters_is_too_short`, `::test_eight_characters_is_enough` |
| Максимальна довжина пароля — 128 | 128 / 129 символів | дозволено / відмова | `iam/test_extra_coverage.py::test_password_of_exactly_max_length_is_accepted`, `iam/test_models.py::TestPasswordPolicy::test_too_long_is_rejected` |
| Некоректні налаштування політики пароля | `min_length=10, max_length=5` | `ValueError` при створенні | `iam/test_models.py::TestPasswordPolicy::test_invalid_configuration_fails_fast` |
| Формат email | `""`, без `@`, без домену, без локальної частини, `@@`, пробіл усередині, крапка на початку/в кінці домену, `..` у домені, 262 символи | `InvalidEmailError` | `iam/test_models.py::TestEmail::test_rejects_malformed` (11 випадків) |
| Регістр і пробіли в email | `"  Olena@Example.COM "` | нормалізується до `olena@example.com` | `iam/test_models.py::TestEmail::test_normalizes_case_and_whitespace` |
| Ім'я користувача — від 1 до 100 символів | `""`, `"   "`, 100 / 101 символ | відмова, відмова, дозволено / відмова | `iam/test_models.py::TestDisplayName::test_rejects_empty_or_too_long`, `::test_accepts_exactly_max_length` |

## 2. Блокування акаунта (FR-005, NFR-SEC-003)

| Межа | Значення в тестах | Очікування | Тест |
|---|---|---|---|
| Поріг — 5 невдалих спроб | 4 / 5 спроб | без блокування / блокування | `iam/test_models.py::TestLockout::test_four_failures_do_not_lock`, `::test_fifth_failure_locks_for_fifteen_minutes`; `iam/test_service.py::TestLockout::test_four_failures_do_not_lock`, `::test_fifth_failure_locks_account` |
| Спроби мають іти «підряд» | 4 невдалі → успіх → ще 4 невдалі | блокування немає | `iam/test_service.py::TestLockout::test_success_resets_consecutive_counter` |
| Тривалість блокування — 15 хв | 14 хв 59 с / рівно 15 хв | ще заблоковано / розблоковано | `iam/test_models.py::TestLockout::test_lock_expires_exactly_at_locked_until`, `iam/test_service.py::TestLockout::test_lock_lifts_after_fifteen_minutes` |
| Спроби під час блокування | 10 спроб у заблокований акаунт | блокування не подовжується | `iam/test_service.py::TestLockout::test_attempts_during_lock_do_not_extend_it` |
| Паралельна атака | 20 одночасних потоків | рівно 5 перевірок пароля, 15 відмов, 1 лист | `iam/test_service.py::TestLockout::test_parallel_attack_gets_exactly_five_attempts` |
| Некоректні налаштування політики | 0 спроб; тривалість 0; тривалість −1 хв | `ValueError` при створенні | `iam/test_extra_coverage.py::test_lockout_policy_with_nonsensical_settings_cannot_be_created` |
| Посилання для розблокування | використано вдруге; після закінчення блокування; вигаданий токен | відмова | `iam/test_service.py::TestUnlockByEmail::test_link_unlocks_immediately_and_only_once`, `::test_link_expires_with_the_lock`, `::test_unknown_token_is_rejected` |
| Збій поштового сервера | SMTP недоступний | блокування все одно діє, відповідь 401, а не 500 | `iam/test_service.py::TestUnlockByEmail::test_mail_failure_does_not_cancel_lock` |

## 3. Реєстрація, вхід і сесії (`src/iam/service.py`)

| Межа | Значення в тестах | Очікування | Тест |
|---|---|---|---|
| Повторний email | той самий email в іншому регістрі й з пробілами | `EmailAlreadyRegisteredError` | `iam/test_service.py::TestRegistration::test_duplicate_email_is_rejected_case_insensitive` |
| Одночасна реєстрація | 10 паралельних реєстрацій одного email | рівно 1 успішна, 9 відмов | `iam/test_service.py::TestRegistration::test_concurrent_registrations_create_one_account` |
| Причина невдалого входу | неправильний пароль; невідомий email; некоректний email | однакова узагальнена помилка (FR-004) | `iam/test_service.py::TestLogin::test_any_failure_is_the_same_generic_error` |
| Невідомий email і атака за часом | вхід з неіснуючим email | хеш однаково перевіряється | `iam/test_service.py::TestLogin::test_unknown_email_still_runs_password_check` |
| Застарілий хеш пароля | `needs_rehash` = True / False | хеш перераховано рівно 1 раз / 0 разів | `iam/test_service.py::TestLogin::test_outdated_hash_is_upgraded_on_login` |
| Простій сесії — 30 хв | 29 хв 59 с / рівно 30 хв | діє / закінчилась | `iam/test_models.py::TestSession::test_expires_after_idle_timeout`, `iam/test_service.py::TestSessions::test_idle_session_expires_after_30_minutes` |
| Абсолютний строк сесії — 12 год | активна сесія: 11 год 40 хв / 12 год | діє / закінчилась навіть при активності | `iam/test_models.py::TestSession::test_expires_at_absolute_lifetime_even_if_active`, `iam/test_service.py::TestSessions::test_absolute_lifetime_ends_active_session` |
| Некоректні налаштування сесії | простій 2 год > строк 1 год | `ValueError` при створенні | `iam/test_models.py::TestSession::test_invalid_configuration_fails_fast` |
| Токен сесії | `""`, 1000 символів, невідомий | `InvalidSessionError` | `iam/test_service.py::TestSessions::test_invalid_tokens_are_rejected` |
| Повторний вихід | `logout` двічі | без помилки (ідемпотентність) | `iam/test_service.py::TestSessions::test_logout_is_idempotent` |
| Користувача видалено, сесія лишилась | `get_by_id` повертає `None` | сесію відхилено й прибрано | `iam/test_extra_coverage.py::test_session_of_deleted_user_is_rejected_and_removed` |

## 4. Права доступу до документів (FR-040–FR-043, NFR-SEC-001, NFR-SEC-004)

| Межа | Значення в тестах | Очікування | Тест |
|---|---|---|---|
| Матриця «роль × дія» | 3 ролі × 4 дії = 12 комбінацій | рівно ті права, що у вимогах | `iam/test_access.py::test_role_matrix` |
| Користувач без ролі | кожна з 4 дій | відмова (default deny) | `iam/test_access.py::test_stranger_is_denied_everything` |
| Роль власника | спроба видати роль Owner іншому; змінити або забрати роль власника | `OwnerAccessChangeError` | `iam/test_access.py::test_owner_cannot_grant_owner_role_to_another_user`, `::test_owner_role_cannot_be_changed_or_revoked` |
| Не-власник керує доступом | editor надає або забирає доступ; guest переглядає учасників | відмова | `iam/test_access.py::test_only_owner_can_share`, `::test_editor_cannot_revoke_access`, `::test_guest_cannot_list_members` |
| Неіснуючий і чужий документ | id 999 і чужий документ для стороннього | однаковий 403, щоб id не можна було підібрати | `api/test_documents_api.py::test_missing_and_foreign_documents_look_the_same` |

## 5. Документи та пагінація (`src/api/main.py`)

| Межа | Значення в тестах | Очікування | Тест |
|---|---|---|---|
| `limit` — від 1 до 100 (`/documents` і `/documents/trash`) | 0, −1, 101, `"abc"` / 1, 100 | 422 / 200 | `api/test_documents_boundaries.py::test_pagination_out_of_range_is_rejected`, `::test_pagination_limit_at_boundary_is_accepted` |
| `offset` — від 0 | −1 | 422 | `api/test_documents_boundaries.py::test_pagination_out_of_range_is_rejected` |
| Прохід по сторінках (3 документи, `limit=2`) | `offset` = 0, 1, 2, 3 (= total), 50 | правильна сторінка й `has_more`; за кінцем списку порожньо, без помилки | `api/test_documents_boundaries.py::test_offset_walks_through_the_list` |
| Порожній список і значення за замовчуванням | немає документів; без параметрів | `total=0`, `has_more=false`; `limit=20`, `offset=0` | `api/test_documents_boundaries.py::test_empty_list_has_no_more_pages`, `::test_default_pagination_is_first_20` |
| `Idempotency-Key` — від 1 до 128 символів | 0 / 1 / 128 / 129 символів; заголовка немає | 422 / 201 / 201 / 422; 422 | `api/test_documents_boundaries.py::test_idempotency_key_length_boundaries`, `::test_missing_idempotency_key_is_rejected` |
| Повтор з тим самим ключем | та сама назва; інша назва; без тіла і з `""` | той самий документ; 409; той самий документ | `api/test_documents_boundaries.py::test_replay_with_same_title_returns_original_document`, `::test_replay_with_different_title_is_conflict`, `::test_replay_without_body_matches_default_title` |
| Ключ діє в межах користувача | однаковий ключ від двох людей | два різні документи | `api/test_documents_api.py::test_idempotency_key_is_per_user` |
| Назва при створенні — до 100 символів | без тіла, `{}`, `""`, `"   "`, `"  План  "`, 100 / 101 символ | «Без назви» ×4, обрізано до «План», дозволено / 422 | `api/test_documents_boundaries.py::test_title_is_normalized`, `::test_title_over_100_characters_is_rejected` |
| Назва при перейменуванні — від 1 до 100 | `""`, `"   "`, 1, 100 / 101 символ | 422, 422, 200, 200 / 422; при 422 стара назва зберігається | `api/test_document_lifecycle.py::test_rename_title_length_boundaries` |
| Право на перейменування | editor / guest | 200 / 403 | `api/test_document_lifecycle.py::test_rename_requires_edit_permission` |
| id документа — додатний | 0, −1 | 422 | `api/test_document_lifecycle.py::test_non_positive_document_id_is_rejected` |
| Документ у кошику | читання, перейменування, повторне видалення, список абзаців, додавання абзацу | 404 | `api/test_document_lifecycle.py::test_trashed_document_is_not_active` |
| Відновлення | активного документа; повторне відновлення | 404; 200, потім 404 | `api/test_document_lifecycle.py::test_restoring_active_document_is_not_found`, `::test_restore_twice_second_is_not_found` |
| Порядок кошика | два документи, видалені з різницею в 1 хв | спершу останній видалений | `api/test_document_lifecycle.py::test_trash_lists_most_recently_deleted_first` |

## 6. Абзаци (`src/api/main.py`)

| Межа | Значення в тестах | Очікування | Тест |
|---|---|---|---|
| Довжина тексту — до 10 000 символів | 10 000 / 10 001 при створенні й редагуванні | дозволено / 422 без змін | `api/test_documents_api.py::test_paragraph_at_limit_is_accepted`, `::test_paragraph_over_limit_is_rejected_on_create`, `::test_paragraph_over_limit_is_rejected_on_update` |
| Порожній текст | `""` | дозволено | `api/test_paragraphs.py::test_empty_content_is_allowed` |
| Позиція вставлення (3 абзаци) | 0, 1, 3 (= len), без позиції / 4 (= len+1), 100, −1 | початок, середина, кінець, кінець / 422 без змін | `api/test_paragraphs.py::test_insert_at_valid_position`, `::test_insert_out_of_range_is_rejected` |
| Вставлення в порожній документ | позиція 0 / 1 | 201 / 422 | `api/test_paragraphs.py::test_insert_into_empty_document` |
| Позиція переміщення (3 абзаци) | перший→останній, останній→перший, на те саме місце, на сусіднє / 3 (= len), −1 | новий порядок / 422 без змін | `api/test_paragraphs.py::test_move_paragraph`, `::test_move_out_of_range_is_rejected` |
| Асиметрія позиції `len` | вставлення на `len` / переміщення на `len` | дозволено (у кінець) / 422 | `api/test_paragraphs.py::test_insert_at_valid_position`, `::test_move_out_of_range_is_rejected` |
| `PATCH` без змін | `{}`; `{"content": null, "position": null}` | 422 | `api/test_paragraphs.py::test_patch_without_changes_is_rejected` |
| Видалення | перший, середній, останній; усі по черзі; той самий двічі | решта перенумерована з 0; порожній документ; 204, потім 404 | `api/test_paragraphs.py::test_delete_renumbers_remaining`, `::test_delete_all_leaves_empty_document`, `::test_delete_twice_second_is_not_found` |
| Неіснуючий абзац | id 999 для GET, PATCH, DELETE | 404 | `api/test_paragraphs.py::test_unknown_paragraph_is_not_found` |
| Абзац з іншого документа | справжній id абзацу, але чужий документ | 404 | `api/test_paragraphs.py::test_paragraph_of_another_document_is_not_found` |
| id абзацу — додатний | 0, −1 | 422 | `api/test_paragraphs.py::test_non_positive_paragraph_id_is_rejected` |
| Інваріант позицій | після кожної зміни | позиції йдуть підряд від 0 без пропусків | перевіряється в `Doc.contents()` у всіх тестах `api/test_paragraphs.py` |

## 7. Час змін (заглушка часу `api_clock`)

| Межа | Значення в тестах | Очікування | Тест |
|---|---|---|---|
| Перейменування | +5 хв після створення | `created_at` без змін, `updated_at` = новий час | `api/test_document_lifecycle.py::test_rename_updates_title_and_timestamp` |
| Кошик і відновлення | +10 хв на кожен крок | точні `deleted_at` і `updated_at` | `api/test_document_lifecycle.py::test_trash_and_restore_record_exact_times` |
| Будь-яка зміна абзацу | додавання, редагування, видалення через +3 хв | `updated_at` документа = новий час | `api/test_paragraphs.py::test_any_paragraph_change_bumps_document_updated_at` |

## 8. Безпека журналів

| Ситуація | Що перевіряється | Тест |
|---|---|---|
| Лист із токеном розблокування за відсутності SMTP | токен не потрапляє в журнал | `iam/test_adapters.py::test_logging_email_sender_does_not_log_unlock_token` |
| Сутність користувача потрапила в журнал | хеш пароля відсутній у `repr` | `iam/test_models.py::TestLockout::test_password_hash_not_in_repr` |
| Відмова в доступі | подія `access_denied` записана | `iam/test_access.py::test_denial_is_logged` |

## Що свідомо не покрито

| Місце | Чому |
|---|---|
| `export_openapi` і `lifespan` у `src/api/main.py` | інфраструктура, а не бізнес-логіка; актуальність специфікації вже перевіряє workflow `deploy-api-docs.yml` |
| `SystemClock.now` і мінімальна довжина токена в `SecretsTokenGenerator` (`src/iam/adapters.py`) | тривіальні адаптери; у тестах їх замінюють дублери |
| Гонки всередині атомарних оновлень у `src/iam/service.py` (рядки 259, 267, 277, 282, 364) | захисні гілки для ситуацій, коли стан змінився між перевіркою та записом; детерміновано відтворити їх можна лише складними моками |

## File was created by Claude, verified and modified by Kozynska Anastasia ##
