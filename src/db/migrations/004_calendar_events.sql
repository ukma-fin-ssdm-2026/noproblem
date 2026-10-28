-- Міграція 004: таблиці подій календаря та їхніх учасників.
--
-- Документи поки зберігаються в пам'яті, тому document_id навмисно
-- не має зовнішнього ключа на documents.

CREATE TABLE calendar_events (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    creator_id  UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title       TEXT NOT NULL
        CHECK (char_length(title) BETWEEN 1 AND 100),
    start_at    TIMESTAMPTZ NOT NULL,
    end_at      TIMESTAMPTZ NOT NULL,
    document_id BIGINT,
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    CONSTRAINT calendar_events_valid_interval CHECK (end_at > start_at)
);

CREATE INDEX calendar_events_creator_range_idx
    ON calendar_events (creator_id, start_at, end_at);

CREATE TABLE calendar_event_participants (
    event_id BIGINT NOT NULL
        REFERENCES calendar_events (id) ON DELETE CASCADE,
    user_id  UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, user_id)
);

CREATE INDEX calendar_event_participants_user_idx
    ON calendar_event_participants (user_id);
