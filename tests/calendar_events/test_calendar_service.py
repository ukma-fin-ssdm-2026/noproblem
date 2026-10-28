"""Calendar service unit tests for FR-063–FR-073."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.calendar_events.models import Event
from src.calendar_events.service import CalendarService
from src.iam import Action

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)
CREATOR_ID = UUID("78c4bb56-c41d-4d64-8f78-5db3632f3480")
PARTICIPANT_ID = UUID("272e5da1-e5fd-48af-a3db-3962f7a10ca5")
OTHER_ID = UUID("8e2c14cf-524a-4daf-aec8-0cae7fd55a62")
DOCUMENT_ID = 42


def event(
    event_id: int = 1,
    *,
    creator_id: UUID = CREATOR_ID,
    title: str = "Planning",
    start_at: datetime = NOW + timedelta(hours=1),
    end_at: datetime = NOW + timedelta(hours=2),
    document_id: int | None = None,
) -> Event:
    return Event(
        id=event_id,
        creator_id=creator_id,
        title=title,
        start_at=start_at,
        end_at=end_at,
        document_id=document_id,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeParticipantRepository:
    def __init__(self) -> None:
        self.participants: dict[int, set[UUID]] = {}

    def add(self, event_id: int, user_id: UUID) -> None:
        self.participants.setdefault(event_id, set()).add(user_id)

    def remove(self, event_id: int, user_id: UUID) -> None:
        self.participants.setdefault(event_id, set()).discard(user_id)

    def list_for_event(self, event_id: int) -> list[UUID]:
        return sorted(self.participants.get(event_id, set()), key=str)


class FakeEventRepository:
    def __init__(self, participants: FakeParticipantRepository) -> None:
        self.participants = participants
        self.events: dict[int, Event] = {}
        self.updates: list[Event] = []
        self.next_id = 1

    def create(self, item: Event) -> Event:
        if item.id == 0:
            item = replace(item, id=self.next_id)
        self.next_id = max(self.next_id, item.id + 1)
        self.events[item.id] = item
        return item

    def get(self, event_id: int) -> Event | None:
        return self.events.get(event_id)

    def update(self, item: Event) -> Event:
        self.events[item.id] = item
        self.updates.append(item)
        return item

    def delete(self, event_id: int) -> None:
        self.events.pop(event_id, None)

    def list_in_range(
        self, user_id: UUID, start: datetime, end: datetime
    ) -> list[Event]:
        return [
            item
            for item in self.events.values()
            if (
                item.creator_id == user_id
                or user_id in self.participants.list_for_event(item.id)
            )
            and item.start_at < end
            and item.end_at > start
        ]


class FakeAccessService:
    def __init__(self) -> None:
        self.document_access: dict[tuple[UUID, int], bool] = {}
        self.check_calls: list[tuple[UUID, int, Action]] = []

    def check(self, user_id: UUID, document_id: int, action: Action) -> None:
        self.check_calls.append((user_id, document_id, action))
        if not self.has_permission(user_id, document_id, action):
            raise PermissionError

    def has_permission(
        self, user_id: UUID, document_id: int, action: Action
    ) -> bool:
        return self.document_access.get((user_id, document_id), False)


@pytest.fixture
def calendar() -> tuple[
    CalendarService,
    FakeEventRepository,
    FakeParticipantRepository,
    FakeAccessService,
]:
    participant_repo = FakeParticipantRepository()
    event_repo = FakeEventRepository(participant_repo)
    access_service = FakeAccessService()
    service = CalendarService(
        event_repo=event_repo,
        participant_repo=participant_repo,
        access_service=access_service,
        find_user_by_email=lambda _email: None,
    )
    return service, event_repo, participant_repo, access_service


@pytest.mark.req("FR-063")
def test_creates_event_with_title_start_and_end(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-063: створена подія зберігає назву, час, завершення й автора."""
    service, event_repo, _, _ = calendar
    start_at = NOW + timedelta(hours=1)
    end_at = NOW + timedelta(hours=2)

    created = service.create_event(CREATOR_ID, "Review", start_at, end_at)

    assert created.title == "Review"
    assert created.start_at == start_at
    assert created.end_at == end_at
    assert created.creator_id == CREATOR_ID
    assert event_repo.get(created.id) == created


@pytest.mark.req("FR-066")
def test_list_in_range_returns_only_overlapping_events(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-066: повертаються події, що перетинаються з часовим вікном."""
    service, event_repo, _, _ = calendar
    window_start = NOW + timedelta(hours=2)
    window_end = NOW + timedelta(hours=4)
    matching = event(
        1,
        start_at=window_start - timedelta(minutes=30),
        end_at=window_start + timedelta(minutes=30),
    )
    ending_at_window_start = event(
        2,
        start_at=window_start - timedelta(hours=1),
        end_at=window_start,
    )
    starting_at_window_end = event(
        3,
        start_at=window_end,
        end_at=window_end + timedelta(hours=1),
    )
    for item in (matching, ending_at_window_start, starting_at_window_end):
        event_repo.create(item)

    results = service.list_in_range(CREATOR_ID, window_start, window_end)

    assert results == [matching]


@pytest.mark.req("FR-067")
def test_creator_can_update_event(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-067: творець може змінити назву й час події, а зміни зберігаються."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event())
    new_start = original.start_at + timedelta(hours=1)
    new_end = original.end_at + timedelta(hours=1)

    updated = service.update_event(
        original.id,
        CREATOR_ID,
        title="Updated planning",
        start_at=new_start,
        end_at=new_end,
    )

    assert updated.title == "Updated planning"
    assert updated.start_at == new_start
    assert updated.end_at == new_end
    assert event_repo.get(original.id) == updated


@pytest.mark.req("FR-067")
def test_non_creator_cannot_update_event(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-067: сторонній користувач не може змінити подію."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event())

    with pytest.raises(PermissionError):
        service.update_event(original.id, OTHER_ID, title="Not allowed")

    assert event_repo.get(original.id) == original


@pytest.mark.req("FR-065")
@pytest.mark.req("FR-067")
def test_update_rejects_end_before_existing_start(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-065/067: не можна задати завершення раніше за збережений початок."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event())

    with pytest.raises(ValueError):
        service.update_event(
            original.id,
            CREATOR_ID,
            end_at=original.start_at - timedelta(seconds=1),
        )

    assert event_repo.get(original.id) == original


@pytest.mark.req("FR-065")
@pytest.mark.req("FR-067")
def test_update_rejects_start_after_existing_end(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-065/067: не можна задати початок пізніше за збережене завершення."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event())

    with pytest.raises(ValueError):
        service.update_event(
            original.id,
            CREATOR_ID,
            start_at=original.end_at + timedelta(seconds=1),
        )

    assert event_repo.get(original.id) == original


@pytest.mark.req("FR-068")
def test_creator_can_delete_event(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-068: творець видаляє подію, і вона зникає зі списку подій."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event())

    service.delete_event(original.id, CREATOR_ID)

    assert event_repo.get(original.id) is None
    assert (
        service.list_in_range(CREATOR_ID, NOW, NOW + timedelta(days=1)) == []
    )


@pytest.mark.req("FR-068")
def test_non_creator_cannot_delete_event(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-068: сторонній користувач не може видалити подію."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event())

    with pytest.raises(PermissionError):
        service.delete_event(original.id, OTHER_ID)

    assert event_repo.get(original.id) == original


@pytest.mark.req("FR-069")
def test_creator_can_add_participant(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-069: творець додає учасника до події."""
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())

    service.add_participant(original.id, CREATOR_ID, PARTICIPANT_ID)

    assert PARTICIPANT_ID in participant_repo.list_for_event(original.id)


def test_creator_cannot_add_self_as_participant(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())

    with pytest.raises(ValueError, match="Творця події не можна додати"):
        service.add_participant(original.id, CREATOR_ID, CREATOR_ID)

    assert CREATOR_ID not in participant_repo.list_for_event(original.id)


@pytest.mark.req("FR-069")
def test_non_creator_cannot_add_participant(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-069: сторонній користувач не може додати учасника до події."""
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())

    with pytest.raises(PermissionError):
        service.add_participant(original.id, OTHER_ID, PARTICIPANT_ID)

    assert participant_repo.list_for_event(original.id) == []


def test_participant_can_list_participants(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """Учасник може переглянути список учасників доступної події."""
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())
    participant_repo.add(original.id, PARTICIPANT_ID)
    participant_repo.add(original.id, OTHER_ID)

    participants = service.list_participants(original.id, PARTICIPANT_ID)

    assert participants == [PARTICIPANT_ID, OTHER_ID]


def test_non_participant_cannot_list_participants(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """Сторонній користувач не може переглянути список учасників."""
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())
    participant_repo.add(original.id, PARTICIPANT_ID)

    with pytest.raises(PermissionError):
        service.list_participants(original.id, OTHER_ID)


@pytest.mark.req("FR-070")
def test_self_removal_does_not_affect_other_participants_calendars(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-070: вихід прибирає подію лише з календаря самого користувача."""
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())
    participant_repo.add(original.id, PARTICIPANT_ID)
    participant_repo.add(original.id, OTHER_ID)

    service.remove_self(original.id, PARTICIPANT_ID)

    window_start = NOW
    window_end = NOW + timedelta(days=1)
    assert (
        service.list_in_range(PARTICIPANT_ID, window_start, window_end) == []
    )
    assert service.list_in_range(OTHER_ID, window_start, window_end) == [
        original
    ]


def test_remove_self_rejects_nonexistent_event(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """Вихід із неіснуючої події завершується помилкою."""
    service, _, participant_repo, _ = calendar

    with pytest.raises(LookupError):
        service.remove_self(999, PARTICIPANT_ID)

    assert participant_repo.list_for_event(999) == []


@pytest.mark.req("FR-071")
def test_creator_can_remove_any_participant(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-071: творець може видалити учасника зі списку події."""
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())
    participant_repo.add(original.id, PARTICIPANT_ID)

    service.remove_participant(original.id, CREATOR_ID, PARTICIPANT_ID)

    assert PARTICIPANT_ID not in participant_repo.list_for_event(original.id)


@pytest.mark.req("FR-071")
def test_non_creator_cannot_remove_other_participant(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-071: не-творець не може видалити іншого учасника."""
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())
    participant_repo.add(original.id, PARTICIPANT_ID)

    with pytest.raises(PermissionError):
        service.remove_participant(original.id, OTHER_ID, PARTICIPANT_ID)

    assert PARTICIPANT_ID in participant_repo.list_for_event(original.id)


@pytest.mark.req("FR-071")
def test_removed_participant_no_longer_sees_event_in_their_range(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-071: видалений учасник більше не бачить подію у своєму календарі."""
    service, event_repo, participant_repo, _ = calendar
    original = event_repo.create(event())
    participant_repo.add(original.id, PARTICIPANT_ID)

    service.remove_participant(original.id, CREATOR_ID, PARTICIPANT_ID)

    assert (
        service.list_in_range(PARTICIPANT_ID, NOW, NOW + timedelta(days=1))
        == []
    )


@pytest.mark.req("FR-072")
def test_creator_can_link_document_when_has_access(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-072: творець прив'язує документ, до якого має доступ на перегляд."""
    service, event_repo, _, access_service = calendar
    original = event_repo.create(event())
    access_service.document_access[(CREATOR_ID, DOCUMENT_ID)] = True

    linked = service.link_document(original.id, CREATOR_ID, DOCUMENT_ID)

    assert linked.document_id == DOCUMENT_ID
    assert event_repo.get(original.id) == linked


@pytest.mark.req("FR-072")
def test_creator_cannot_link_document_without_access(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-072: без доступу перевіряється VIEW і прив'язування відхиляється."""
    service, event_repo, _, access_service = calendar
    original = event_repo.create(event())

    with pytest.raises(PermissionError):
        service.link_document(original.id, CREATOR_ID, DOCUMENT_ID)

    assert access_service.check_calls == [
        (CREATOR_ID, DOCUMENT_ID, Action.VIEW)
    ]
    assert event_repo.get(original.id) == original


def test_creator_can_unlink_document(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """Творець може явно відв'язати документ від події."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event(document_id=DOCUMENT_ID))

    unlinked = service.unlink_document(original.id, CREATOR_ID)

    assert unlinked.document_id is None
    assert unlinked.updated_at > original.updated_at
    assert event_repo.get(original.id) == unlinked


def test_unlinking_event_without_document_does_not_update_it(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    service, event_repo, _, _ = calendar
    original = event_repo.create(event())

    unchanged = service.unlink_document(original.id, CREATOR_ID)

    assert unchanged == original
    assert event_repo.updates == []


def test_non_creator_cannot_unlink_document(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """Не-творець не може відв'язати документ від події."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event(document_id=DOCUMENT_ID))

    with pytest.raises(PermissionError):
        service.unlink_document(original.id, OTHER_ID)

    assert event_repo.get(original.id) == original


@pytest.mark.req("FR-072")
def test_non_creator_cannot_link_document(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-072: не-творець не може прив'язати документ навіть з доступом."""
    service, event_repo, _, access_service = calendar
    original = event_repo.create(event())
    access_service.document_access[(OTHER_ID, DOCUMENT_ID)] = True

    with pytest.raises(PermissionError):
        service.link_document(original.id, OTHER_ID, DOCUMENT_ID)

    assert access_service.check_calls == []
    assert event_repo.get(original.id) == original


@pytest.mark.req("FR-073")
def test_document_auto_unlinked_when_creator_access_revoked(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-073: відкликання доступу творця автоматично відв'язує документ."""
    service, event_repo, _, access_service = calendar
    original = event_repo.create(event())
    access_service.document_access[(CREATOR_ID, DOCUMENT_ID)] = True
    linked = service.link_document(original.id, CREATOR_ID, DOCUMENT_ID)
    access_service.document_access[(CREATOR_ID, DOCUMENT_ID)] = False

    retrieved = service.get_event(original.id, CREATOR_ID)

    assert retrieved.document_id is None
    assert event_repo.updates[-1] == retrieved
    assert linked.document_id == DOCUMENT_ID


@pytest.mark.req("FR-073")
def test_document_auto_unlinked_when_creator_access_revoked_from_calendar_list(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-073: список календаря відв'язує недоступний документ."""
    service, event_repo, participant_repo, access_service = calendar
    original = event_repo.create(event())
    participant_repo.add(original.id, PARTICIPANT_ID)
    access_service.document_access[(CREATOR_ID, DOCUMENT_ID)] = True
    service.link_document(original.id, CREATOR_ID, DOCUMENT_ID)
    access_service.document_access[(CREATOR_ID, DOCUMENT_ID)] = False

    listed = service.list_in_range(
        PARTICIPANT_ID, NOW, NOW + timedelta(days=1)
    )

    assert len(listed) == 1
    assert listed[0].document_id is None
    assert event_repo.get(original.id) == listed[0]


@pytest.mark.req("FR-066")
def test_user_without_participation_cannot_view_event(
    calendar: tuple[
        CalendarService,
        FakeEventRepository,
        FakeParticipantRepository,
        FakeAccessService,
    ],
) -> None:
    """FR-066: Користувач без участі не може переглянути подію."""
    service, event_repo, _, _ = calendar
    original = event_repo.create(event())

    with pytest.raises(PermissionError):
        service.get_event(original.id, OTHER_ID)

    assert event_repo.get(original.id) == original


# File was created by Copilot and reviewed by Olha Marushchenko
