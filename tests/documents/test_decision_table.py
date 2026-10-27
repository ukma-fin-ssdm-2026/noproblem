"""Бонус 2: таблиця рішень «роль × стан документа × операція».

Результат операції з документом залежить від трьох умов, і порядок
перевірок важливий: спершу права (I-11), потім стан документа. Тому,
наприклад, Editor отримує 403 на відновлення навіть документа з кошика,
а Owner — 404, якщо відновлює активний документ.

Таблиця скорочена: «—» (будь-яке значення) і перелік операцій в одній
клітинці об'єднують комбінації з однаковим результатом. Одне правило =
один тестовий випадок з ID ``R01``…``R11``; усередині випадку
перевіряються всі комбінації, які правило покриває, кожна на свіжому
документі. Сама таблиця — у ``docs/validation/test-plan.md``, розділ
«Бонуси».
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product
from uuid import UUID

import pytest

from src.documents.bootstrap import build_documents
from src.documents.errors import DocumentNotFoundError, DocumentNotInTrashError
from src.documents.service import DocumentService
from src.iam import Role
from src.iam.errors import AccessDeniedError
from tests.conftest import VALID_PASSWORD, IamTestEnv

ACTIVE, TRASHED = "активний", "у кошику"
ANY_STATE = (ACTIVE, TRASHED)

OPERATIONS: dict[str, Callable[[DocumentService, UUID, int], object]] = {
    "прочитати": lambda s, user, doc: s.get(user, doc),
    "перейменувати": lambda s, user, doc: s.rename(user, doc, "Нова назва"),
    "в кошик": lambda s, user, doc: s.move_to_trash(user, doc),
    "відновити": lambda s, user, doc: s.restore(user, doc),
}
ANY_OPERATION = tuple(OPERATIONS)
ROLES = (Role.OWNER, Role.EDITOR, Role.GUEST, None)  # None — без ролі

ALLOWED = None  # операція виконується без винятку
Outcome = type[Exception] | None


@dataclass(frozen=True)
class Rule:
    id: str
    role: Role | None
    states: tuple[str, ...]
    operations: tuple[str, ...]
    outcome: Outcome


RULES = (
    Rule("R01", None, ANY_STATE, ANY_OPERATION, AccessDeniedError),
    Rule(
        "R02",
        Role.OWNER,
        (ACTIVE,),
        ("прочитати", "перейменувати", "в кошик"),
        ALLOWED,
    ),
    Rule(
        "R03",
        Role.OWNER,
        (ACTIVE,),
        ("відновити",),
        DocumentNotInTrashError,
    ),
    Rule(
        "R04",
        Role.OWNER,
        (TRASHED,),
        ("прочитати", "перейменувати", "в кошик"),
        DocumentNotFoundError,
    ),
    Rule("R05", Role.OWNER, (TRASHED,), ("відновити",), ALLOWED),
    Rule(
        "R06",
        Role.EDITOR,
        (ACTIVE,),
        ("прочитати", "перейменувати"),
        ALLOWED,
    ),
    Rule(
        "R07",
        Role.EDITOR,
        (TRASHED,),
        ("прочитати", "перейменувати"),
        DocumentNotFoundError,
    ),
    Rule(
        "R08",
        Role.EDITOR,
        ANY_STATE,
        ("в кошик", "відновити"),
        AccessDeniedError,
    ),
    Rule("R09", Role.GUEST, (ACTIVE,), ("прочитати",), ALLOWED),
    Rule("R10", Role.GUEST, (TRASHED,), ("прочитати",), DocumentNotFoundError),
    Rule(
        "R11",
        Role.GUEST,
        ANY_STATE,
        ("перейменувати", "в кошик", "відновити"),
        AccessDeniedError,
    ),
)


def register(env: IamTestEnv, email: str) -> UUID:
    return env.iam.register(email, email.split("@")[0], VALID_PASSWORD).user.id


def run(operation: Callable[[], object]) -> Outcome:
    """Виконує операцію й повертає клас винятку або ``ALLOWED``."""
    try:
        operation()
    except (
        AccessDeniedError,
        DocumentNotFoundError,
        DocumentNotInTrashError,
    ) as error:
        return type(error)
    return ALLOWED


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.id)
def test_document_decision_table(env: IamTestEnv, rule: Rule) -> None:
    module = build_documents(env.access, clock=env.clock)
    env.access.bind_documents(module.documents)  # як у create_app
    service = module.service
    owner = register(env, "owner@example.com")
    actor = owner if rule.role is Role.OWNER else register(env, "actor@x.com")

    combinations = product(rule.states, rule.operations)
    for number, (state, operation) in enumerate(combinations):
        created = service.create(owner, f"doc-{number}", "Документ")
        document_id = created.document.id
        if rule.role in (Role.EDITOR, Role.GUEST):
            env.access.share(owner, document_id, "actor@x.com", rule.role)
        if state == TRASHED:
            service.move_to_trash(owner, document_id)

        outcome = run(
            lambda: OPERATIONS[operation](service, actor, document_id)
        )
        assert outcome is rule.outcome, f"{rule.id}: {state}, {operation}"


def test_decision_table_covers_every_combination_once() -> None:
    """Таблиця повна й несуперечлива: 4 × 2 × 4 = 32, без перетинів."""
    covered = [
        (rule.role, state, operation)
        for rule in RULES
        for state in rule.states
        for operation in rule.operations
    ]
    assert len(covered) == len(set(covered))
    assert set(covered) == set(product(ROLES, ANY_STATE, ANY_OPERATION))


# File was created by Claude. Reviewed by Kozynska Anastasia
