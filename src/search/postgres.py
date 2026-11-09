"""PostgreSQL-адаптер пошуку документів."""

from __future__ import annotations

from collections.abc import Collection
import logging

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

from src.search.errors import SearchUnavailableError
from src.search.models import SearchMatch

logger = logging.getLogger("notely.search")


class PostgresSearchRepository:
    """Шукає активні документи в PostgreSQL за назвою й абзацами."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def find_matches(
        self, document_ids: Collection[int], query: str, limit: int
    ) -> list[SearchMatch]:
        ids = list(document_ids)
        if not ids:
            return []

        escaped_query = (
            query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped_query}%"
        try:
            with self._pool.connection() as conn:
                with conn.transaction():
                    conn.execute("SET LOCAL statement_timeout = '2s'")
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
                        LIMIT %s
                        """,
                        (pattern, pattern, ids, pattern, limit),
                    ).fetchall()
        except (psycopg.errors.QueryCanceled, PoolTimeout) as exc:
            logger.exception("Пошук у PostgreSQL тимчасово недоступний.")
            raise SearchUnavailableError() from exc
        return [
            SearchMatch(
                doc_id=row["id"],
                title=row["title"],
                matched_text=row["matched_text"],
            )
            for row in rows
        ]
