-- Align version snapshots with the agreed VersionParagraph shape.
ALTER TABLE document_versions
    RENAME COLUMN content_snapshot TO paragraphs;

UPDATE document_versions AS version
SET paragraphs = COALESCE(
    (
        SELECT jsonb_agg(
            jsonb_build_object(
                'position', paragraph.value -> 'position',
                'content', paragraph.value -> 'content'
            )
            ORDER BY (paragraph.value ->> 'position')::integer
        )
        FROM jsonb_array_elements(version.paragraphs) AS paragraph(value)
    ),
    '[]'::jsonb
);
