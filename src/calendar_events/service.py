from dataclasses import replace
from datetime import datetime, timezone
from collections.abc import Callable
from uuid import UUID

from src.calendar_events.ports import EventRepository, ParticipantRepository
from src.calendar_events.models import Event
from src.iam import AccessService, Action, UserView
from src.iam.errors import UserNotFoundError


class EventNotFoundError(LookupError):
    """Подію календаря не знайдено."""


class CalendarAccessDeniedError(PermissionError):
    """Користувач не має права виконати дію з подією."""


class InvalidEventError(ValueError):
    """Дані події не відповідають доменним правилам."""


class CalendarService:
    def __init__(
        self,
        *,
        event_repo: EventRepository,
        participant_repo: ParticipantRepository,
        access_service: AccessService,
        find_user_by_email: Callable[[str], UserView | None],
    ) -> None:
        self._event_repo = event_repo
        self._participant_repo = participant_repo
        self._access_service = access_service
        self._find_user_by_email = find_user_by_email

    def list_in_range(
        self, user_id: UUID, start: datetime, end: datetime
    ) -> list[Event]:
        """Повертає події користувача, що перетинаються з часовим вікном."""
        events = self._event_repo.list_in_range(user_id, start, end)
        return [
            self._unlink_document_if_creator_access_revoked(event)
            for event in events
        ]

    def _require_creator(self, event_id: int, actor_id: UUID) -> Event:
        """Повертає подію, якщо її створив actor_id, інакше відмовляє."""
        event = self._event_repo.get(event_id)
        if event is None:
            raise EventNotFoundError(f"Подію {event_id} не знайдено.")
        if event.creator_id != actor_id:
            raise CalendarAccessDeniedError
        return event

    def _require_access(self, event_id: int, user_id: UUID) -> Event:
        """Повертає подію лише її творцю або зареєстрованому учаснику."""
        event = self._event_repo.get(event_id)
        if event is None:
            raise EventNotFoundError(f"Подію {event_id} не знайдено.")
        if (
            event.creator_id != user_id
            and user_id not in self._participant_repo.list_for_event(event_id)
        ):
            raise CalendarAccessDeniedError
        return event

    def create_event(
        self,
        creator_id: UUID,
        title: str,
        start_at: datetime,
        end_at: datetime,
    ) -> Event:
        """Створює подію (FR-063), вимагаючи коректний інтервал (FR-065).

        Наявність назви й часу початку перевіряє API-модель (FR-064).
        """
        if end_at <= start_at:
            raise InvalidEventError(
                "Час завершення має бути пізніше за час початку."
            )
        now = datetime.now(timezone.utc)
        event = Event(
            id=0,
            creator_id=creator_id,
            title=title,
            start_at=start_at,
            end_at=end_at,
            document_id=None,
            created_at=now,
            updated_at=now,
        )
        return self._event_repo.create(event)

    def update_event(
        self,
        event_id: int,
        actor_id: UUID,
        *,
        title: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Event:
        """Творець змінює подію (FR-067) з перевіркою інтервалу (FR-065)."""
        event = self._require_creator(event_id, actor_id)
        final_start = event.start_at if start_at is None else start_at
        final_end = event.end_at if end_at is None else end_at
        if final_end <= final_start:
            raise InvalidEventError(
                "Час завершення має бути пізніше за час початку."
            )
        updated = replace(
            event,
            title=event.title if title is None else title,
            start_at=final_start,
            end_at=final_end,
            updated_at=datetime.now(timezone.utc),
        )
        return self._event_repo.update(updated)

    def delete_event(self, event_id: int, actor_id: UUID) -> None:
        """Видаляє подію, якщо запит виконує її творець (FR-068)."""
        self._require_creator(event_id, actor_id)
        self._event_repo.delete(event_id)

    def add_participant(
        self, event_id: int, actor_id: UUID, participant_id: UUID
    ) -> None:
        """Додає учасника до події за запитом творця (FR-069)."""
        event = self._require_creator(event_id, actor_id)
        if participant_id == event.creator_id:
            raise InvalidEventError(
                "Творця події не можна додати як учасника."
            )
        self._participant_repo.add(event_id, participant_id)

    def add_participant_by_email(
        self, event_id: int, actor_id: UUID, email: str
    ) -> None:
        """Додає зареєстрованого користувача за email після перевірки творця.

        Перевірка творця перед пошуком не дозволяє стороннім перевіряти,
        чи зареєстрований певний email.
        """
        event = self._require_creator(event_id, actor_id)
        participant = self._find_user_by_email(email)
        if participant is None:
            raise UserNotFoundError()
        if participant.id == event.creator_id:
            raise InvalidEventError(
                "Творця події не можна додати як учасника."
            )
        self._participant_repo.add(event_id, participant.id)

    def list_participants(self, event_id: int, user_id: UUID) -> list[UUID]:
        """Повертає учасників події, доступної творцю або учаснику."""
        self._require_access(event_id, user_id)
        return self._participant_repo.list_for_event(event_id)

    def remove_self(self, event_id: int, user_id: UUID) -> None:
        """Дозволяє учаснику вийти з наявної події (FR-070)."""
        event = self._event_repo.get(event_id)
        if event is None:
            raise EventNotFoundError(f"Подію {event_id} не знайдено.")
        if event.creator_id == user_id:
            raise CalendarAccessDeniedError
        self._participant_repo.remove(event_id, user_id)

    def remove_participant(
        self, event_id: int, actor_id: UUID, participant_id: UUID
    ) -> None:
        """Дозволяє творцю видалити учасника події (FR-071)."""
        self._require_creator(event_id, actor_id)
        self._participant_repo.remove(event_id, participant_id)

    def link_document(
        self, event_id: int, actor_id: UUID, document_id: int
    ) -> Event:
        """Прив'язує документ після перевірок творця й доступу VIEW
        (FR-072).
        """
        event = self._require_creator(event_id, actor_id)
        self._access_service.check(actor_id, document_id, Action.VIEW)
        updated = replace(
            event,
            document_id=document_id,
            updated_at=datetime.now(timezone.utc),
        )
        return self._event_repo.update(updated)

    def unlink_document(self, event_id: int, actor_id: UUID) -> Event:
        """Явно відв'язує документ від події за запитом творця."""
        event = self._require_creator(event_id, actor_id)
        if event.document_id is None:
            return event
        updated = replace(
            event,
            document_id=None,
            updated_at=datetime.now(timezone.utc),
        )
        return self._event_repo.update(updated)

    def get_event(self, event_id: int, user_id: UUID) -> Event:
        """Повертає доступну подію й відв'язує документ без доступу
        творця (FR-073).
        """
        event = self._require_access(event_id, user_id)
        return self._unlink_document_if_creator_access_revoked(event)

    def _unlink_document_if_creator_access_revoked(
        self, event: Event
    ) -> Event:
        if (
            event.document_id is not None
            and not self._access_service.has_permission(
                event.creator_id, event.document_id, Action.VIEW
            )
        ):
            return self._event_repo.update(
                replace(
                    event,
                    document_id=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        return event


# File was created by Copilot and reviewed by Olha Marushchenko
