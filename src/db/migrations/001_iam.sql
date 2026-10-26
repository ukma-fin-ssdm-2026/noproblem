-- Міграція 001: таблиці модуля IAM (data-model.md, ADR-002).
--
-- Час — лише TIMESTAMPTZ: IAM порівнює моменти з часовим поясом
-- (блокування на 15 хв, строк сесії), а звичайний TIMESTAMP дав би
-- зсуви на кілька годин.
--
-- document_access.document_id поки НЕ має зовнішнього ключа на
-- documents: модулі переходять на PostgreSQL по черзі, і поки
-- документи живуть у пам'яті, такий ключ блокував би запис ролей.
-- Ключ додасть окрема міграція, коли всі модулі будуть у базі.

CREATE TABLE users (
    id                    UUID PRIMARY KEY,
    email                 TEXT NOT NULL UNIQUE,
    name                  TEXT NOT NULL,
    password_hash         TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0
        CHECK (failed_login_attempts >= 0),
    locked_until          TIMESTAMPTZ
);

CREATE TABLE sessions (
    id           UUID PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash   TEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX sessions_user_id_idx ON sessions (user_id);

CREATE TABLE unlock_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);

-- Одна роль на пару «документ + користувач», як у
-- InMemoryAccessRepository; тому складений первинний ключ.
CREATE TABLE document_access (
    document_id BIGINT NOT NULL,
    user_id     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'guest')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, user_id)
);

CREATE INDEX document_access_user_id_idx ON document_access (user_id);

-- File was created by Claude. Reviewed by Kozynska Anastasia
