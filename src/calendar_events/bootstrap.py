"""Composition root for the calendar service."""

from __future__ import annotations

from dataclasses import dataclass

from src.calendar_events.adapters import InMemoryCalendarRepository
from src.calendar_events.service import CalendarService
from src.iam import AccessService, AuthService


@dataclass(frozen=True)
class CalendarModule:
    service: CalendarService
    repository: InMemoryCalendarRepository


def build_calendar(
    access_service: AccessService, auth_service: AuthService
) -> CalendarModule:
    repository = InMemoryCalendarRepository()
    service = CalendarService(
        event_repo=repository,
        participant_repo=repository,
        access_service=access_service,
        find_user_by_email=auth_service.find_user_by_email,
    )
    return CalendarModule(service=service, repository=repository)
