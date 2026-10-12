"""Модуль «Документи та версії» (Docs). КАРКАС.

Відповідальність (high-level-design, розділ 2): документи, назви,
кошик, абзаци, знімки та історія версій.

Інтерфейси:
    * I-06 REST API → Docs: CRUD документів, кошик, версії;
    * I-10 Collab → Docs: автозбереження, знімки версій;
    * I-11 Docs → IAM: перевірка права перед КОЖНОЮ операцією
      (``IamModule``, частина 2 реалізації IAM);
    * I-14 Docs → DB; I-18 Scheduler → Docs.

Стан: демонстраційна логіка поки міститься в ``src/api/main.py``.
План — винести її сюди за шаблоном модуля ``src/iam``::

    documents/
    ├── domain/          Document, Paragraph, правила назви (FR-015, FR-016)
    ├── application/     сценарії + порти (DocumentRepository, ...)
    ├── infrastructure/  in-memory → PostgreSQL (ADR-002)
    └── module.py        фасад DocumentsModule
"""
