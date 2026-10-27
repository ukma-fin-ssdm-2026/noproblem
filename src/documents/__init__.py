"""Модуль «Документи та версії» (Docs).

Відповідальність (high-level-design, розділ 2): документи, назви,
кошик, абзаци; згодом — знімки та історія версій (FR-030–FR-032).

Інтерфейси:
    * I-06 REST API → Docs: маршрути в ``src/api/documents.py``;
    * I-10 Collab → Docs: автозбереження, знімки версій (згодом);
    * I-11 Docs → IAM: перевірка права перед КОЖНОЮ операцією;
    * I-14 Docs → DB; I-18 Scheduler → Docs.

Структура (за шаблоном ``src/iam``)::

    documents/
    ├── models.py     Document, Paragraph, AccessMode, Page
    ├── errors.py     винятки модуля (без HTTP)
    ├── ports.py      DocumentRepository, ParagraphRepository
    ├── service.py    DocumentService: сценарії й правила
    ├── adapters.py   сховища в пам'яті
    └── bootstrap.py  build_documents(): збирання модуля

PostgreSQL-сховища тих самих портів додаються в ``postgres.py``.
"""

# File was created by Claude. Reviewed by Kozynska Anastasia
