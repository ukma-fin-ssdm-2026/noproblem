-- Міграція 003: запити на доступ і зміну ролі (FR-047–FR-051,
-- підготовка до FR-053–FR-056).
--
-- document_id поки без FK: документи ще зберігаються в пам'яті,
-- а document_access не має такого FK з тієї ж причини.

CREATE TABLE access_requests (
    id             UUID PRIMARY KEY,
    document_id    BIGINT NOT NULL,
    requester_id   UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    request_type   TEXT NOT NULL CHECK (request_type IN ('access', 'role')),
    requested_role TEXT CHECK (requested_role IN ('editor')),
    status         TEXT NOT NULL
        CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at     TIMESTAMPTZ NOT NULL,
    resolved_at    TIMESTAMPTZ,
    CHECK (
        (request_type = 'access' AND requested_role IS NULL)
        OR (request_type = 'role' AND requested_role = 'editor')
    ),
    CHECK (
        (status = 'pending' AND resolved_at IS NULL)
        OR (status IN ('approved', 'rejected') AND resolved_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX access_requests_one_pending_per_type
    ON access_requests (document_id, requester_id, request_type)
    WHERE status = 'pending';

CREATE INDEX access_requests_document_status_idx
    ON access_requests (document_id, status, created_at);

CREATE INDEX access_requests_requester_created_idx
    ON access_requests (requester_id, created_at DESC);
