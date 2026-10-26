-- Міграція 002: таблиці модуля «Документи» (data-model.md, ADR-001,
-- ADR-002).
--
-- Відмінності від data-model.md:
--   * немає is_deleted: «документ у кошику» = deleted_at IS NOT NULL,
--     так немає двох полів, які можуть суперечити одне одному;
--   * немає owner_id: власник — запис з роллю 'owner' у
--     document_access, IAM лишається єдиним джерелом правди про ролі.
-- Зовнішніх ключів на users немає з тієї ж причини, що й у 001:
-- модулі переходять на PostgreSQL по черзі.

CREATE TABLE documents (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT NOT NULL
        CHECK (char_length(title) BETWEEN 1 AND 100),
    access_mode TEXT NOT NULL DEFAULT 'restricted'
        CHECK (access_mode IN ('restricted', 'link')),
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    deleted_at  TIMESTAMPTZ 
);

-- Планувальник шукає документи, що лежать у кошику понад 30 днів
-- (FR-023); частковий індекс містить лише документи з кошика.
CREATE INDEX documents_deleted_at_idx
    ON documents (deleted_at) WHERE deleted_at IS NOT NULL;

-- Позиції абзаців унікальні в межах документа. Перевірку відкладено
-- до кінця транзакції (DEFERRABLE INITIALLY DEFERRED): під час
-- перенумерації два абзаци на мить мають однакову позицію, і
-- негайна перевірка зламала б коректну операцію.
CREATE TABLE paragraphs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id BIGINT NOT NULL
        REFERENCES documents (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL CHECK (position >= 0),
    content     TEXT NOT NULL CHECK (char_length(content) <= 10000),
    CONSTRAINT paragraphs_document_position_key
        UNIQUE (document_id, position) DEFERRABLE INITIALLY DEFERRED
);

-- Ключ ідемпотентності діє в межах користувача (FR-013). Запис
-- з'являється в тій самій транзакції, що й документ, і зникає разом
-- із ним (ON DELETE CASCADE).
CREATE TABLE idempotency_keys (
    user_id         UUID NOT NULL,
    key             TEXT NOT NULL CHECK (char_length(key) BETWEEN 1 AND 128),
    requested_title TEXT NOT NULL,
    document_id     BIGINT NOT NULL
        REFERENCES documents (id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, key)
);

-- File was created by Claude. Reviewed by Kozynska Anastasia
