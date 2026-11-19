-- Version history snapshots (FR-030).
-- author_id intentionally has no IAM foreign key, as in 002_documents.sql.
CREATE TABLE document_versions (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id      BIGINT NOT NULL
        REFERENCES documents (id) ON DELETE CASCADE,
    author_id        UUID NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL,
    content_snapshot JSONB NOT NULL
);

CREATE INDEX document_versions_document_created_idx
    ON document_versions (document_id, created_at DESC, id DESC);
