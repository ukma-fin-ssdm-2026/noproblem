"""Composition root for the calendar service."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from src.calendar_events.adapters import InMemoryCalendarRepository
from src.calendar_events.ports import CalendarRepository
from src.calendar_events.postgres import PostgresCalendarRepository
from src.calendar_events.service import CalendarService
from src.iam import AccessService, AuthService


@dataclass(frozen=True)
class CalendarModule:
    service: CalendarService
    repository: CalendarRepository


def build_calendar(
    access_service: AccessService,
    auth_service: AuthService,
    pool: ConnectionPool | None = None,
) -> CalendarModule:
    repository: CalendarRepository
    repository = (
        PostgresCalendarRepository(pool)
        if pool is not None
        else InMemoryCalendarRepository()
    )
    service = CalendarService(
        event_repo=repository,
        participant_repo=repository,
        access_service=access_service,
        find_user_by_email=auth_service.find_user_by_email,
    )
    return CalendarModule(service=service, repository=repository)


# File was created by Copilot and reviewed by Olha Marushchenko
