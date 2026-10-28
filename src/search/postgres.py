"""PostgreSQL-адаптер пошуку документів."""

from __future__ import annotations

from collections.abc import Collection

from psycopg_pool import ConnectionPool

from src.search.models import SearchMatch


class PostgresSearchRepository:
    """Шукає активні документи в PostgreSQL за назвою й абзацами."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def find_matches(
        self, document_ids: Collection[int], query: str
    ) -> list[SearchMatch]:
        ids = list(document_ids)
        if not ids:
            return []

        escaped_query = (
            query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped_query}%"
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.title,
                       CASE
                           WHEN d.title ILIKE %s THEN d.title
                           ELSE matching_paragraph.content
                       END AS matched_text
                FROM documents AS d
                LEFT JOIN LATERAL (
                    SELECT p.content
                    FROM paragraphs AS p
                    WHERE p.document_id = d.id AND p.content ILIKE %s
                    ORDER BY p.position
                    LIMIT 1
                ) AS matching_paragraph ON true
                WHERE d.id = ANY(%s)
                  AND d.deleted_at IS NULL
                  AND (
                      d.title ILIKE %s
                      OR matching_paragraph.content IS NOT NULL
                  )
                ORDER BY d.id
                """,
                (pattern, pattern, ids, pattern),
            ).fetchall()
        return [
            SearchMatch(
                doc_id=row["id"],
                title=row["title"],
                matched_text=row["matched_text"],
            )
            for row in rows
        ]
