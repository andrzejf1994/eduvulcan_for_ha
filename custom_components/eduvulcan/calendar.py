"""Calendar entities for EduVulcan for HA."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, KIND_EXAMS, KIND_HOMEWORK, KIND_SCHEDULE
from .coordinator import EduVulcanCoordinator


@dataclass(frozen=True)
class CalendarDefinition:
    """Definition for a calendar entity."""

    kind: str
    name_suffix: str
    all_day: bool


CALENDARS: tuple[CalendarDefinition, ...] = (
    CalendarDefinition(kind=KIND_SCHEDULE, name_suffix="Plan Lekcji", all_day=False),
    CalendarDefinition(kind=KIND_HOMEWORK, name_suffix="Zadania", all_day=True),
    CalendarDefinition(kind=KIND_EXAMS, name_suffix="Sprawdziany", all_day=True),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EduVulcan calendar entities."""
    coordinator: EduVulcanCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [EduVulcanCalendarEntity(coordinator, calendar) for calendar in CALENDARS]
    async_add_entities(entities)


class EduVulcanCalendarEntity(CoordinatorEntity, CalendarEntity):
    """Representation of an EduVulcan calendar."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: EduVulcanCoordinator,
        definition: CalendarDefinition,
    ) -> None:
        super().__init__(coordinator)
        self._definition = definition
        name = (coordinator.data or {}).get("name") or "EduVulcan"
        slug = (coordinator.data or {}).get("slug") or "eduvulcan"
        uid = (coordinator.data or {}).get("uid") or "unknown"
        self._attr_name = f"{name} {definition.name_suffix}"
        self._attr_unique_id = f"{uid}_{definition.kind}"
        self.entity_id = f"calendar.eduvulcan_{slug}_{definition.kind}"

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        data = self.coordinator.data or {}
        items = data.get(self._definition.kind, [])
        tz = dt_util.get_time_zone(hass.config.time_zone)
        events: list[CalendarEvent] = []
        for item in items:
            event = self._build_event(item, tz)
            if event is None:
                continue
            if _event_in_range(event, start_date, end_date, tz):
                events.append(event)
        return events

    def _build_event(self, item: object, tz) -> CalendarEvent | None:
        account_info = self.coordinator.account_info
        if self._definition.kind == KIND_SCHEDULE:
            return _build_lesson_event(item, account_info, tz)
        if self._definition.kind == KIND_HOMEWORK:
            return _build_homework_event(item, account_info)
        if self._definition.kind == KIND_EXAMS:
            return _build_exam_event(item, account_info)
        return None


def _event_in_range(
    event: CalendarEvent,
    start_range: datetime,
    end_range: datetime,
    tz,
) -> bool:
    start = _normalize_event_datetime(event.start, tz)
    end = _normalize_event_datetime(event.end, tz)
    return start < end_range and end > start_range


def _normalize_event_datetime(value: datetime | date, tz) -> datetime:
    if isinstance(value, datetime):
        return dt_util.as_utc(value)
    return dt_util.as_utc(datetime.combine(value, time.min, tzinfo=tz))


def _build_lesson_event(item: object, account_info, tz) -> CalendarEvent | None:
    subject_name = item.subject.name if getattr(item, "subject", None) else None
    room_code = getattr(getattr(item, "room", None), "code", None)
    if not getattr(item, "time_slot", None):
        return None
    summary = subject_name or item.event or "Lekcja"
    if room_code:
        summary = f"{summary} ({room_code})"
    start_dt = datetime.combine(item.date_, item.time_slot.start, tzinfo=tz)
    end_dt = datetime.combine(item.date_, item.time_slot.end, tzinfo=tz)
    description_lines = []
    _add_common_account_lines(description_lines, account_info)
    _add_line(description_lines, "Przedmiot", subject_name)
    _add_line(description_lines, "Sala", room_code)
    _add_line(description_lines, "Klasa", getattr(getattr(item, "clazz", None), "symbol", None))
    _add_line(
        description_lines,
        "Nauczyciel",
        _teacher_name(getattr(item, "teacher_primary", None)),
    )
    _add_line(
        description_lines,
        "Nauczyciel dodatkowy",
        _teacher_name(getattr(item, "teacher_secondary", None)),
    )
    _add_line(
        description_lines,
        "Uwagi",
        getattr(item, "event", None),
    )
    return CalendarEvent(
        summary=summary,
        start=start_dt,
        end=end_dt,
        description="\n".join(description_lines),
        location=room_code,
    )


def _build_homework_event(item: object, account_info) -> CalendarEvent:
    subject_name = item.subject.name if getattr(item, "subject", None) else None
    summary = f"{subject_name} – Zadanie" if subject_name else "Zadanie"
    deadline = getattr(item, "deadline", None) or getattr(item, "date_", None)
    start_date = deadline.date() if isinstance(deadline, datetime) else deadline
    if not start_date:
        start_date = date.today()
    end_date = start_date + timedelta(days=1)
    description_lines = []
    _add_common_account_lines(description_lines, account_info)
    _add_line(description_lines, "Przedmiot", subject_name)
    _add_line(description_lines, "Termin", getattr(item, "deadline", None))
    _add_line(description_lines, "Opis", getattr(item, "content", None))
    _add_line(
        description_lines,
        "Nauczyciel",
        _teacher_name(getattr(item, "creator", None)),
    )
    _add_line(
        description_lines,
        "Wymaga odpowiedzi",
        getattr(item, "is_answer_required", None),
    )
    attachments = getattr(item, "attachments", [])
    if attachments:
        _add_line(description_lines, "Załączniki", ", ".join(a.name for a in attachments))
        _add_line(
            description_lines,
            "Linki",
            ", ".join(a.link for a in attachments),
        )
    return CalendarEvent(
        summary=summary,
        start=start_date,
        end=end_date,
        description="\n".join(description_lines),
    )


def _build_exam_event(item: object, account_info) -> CalendarEvent:
    subject_name = item.subject.name if getattr(item, "subject", None) else None
    summary = f"{subject_name} – Sprawdzian" if subject_name else "Sprawdzian"
    deadline = getattr(item, "deadline", None)
    start_date = deadline.date() if isinstance(deadline, datetime) else deadline
    if not start_date:
        start_date = date.today()
    end_date = start_date + timedelta(days=1)
    description_lines = []
    _add_common_account_lines(description_lines, account_info)
    _add_line(description_lines, "Przedmiot", subject_name)
    _add_line(description_lines, "Typ", getattr(item, "type", None))
    _add_line(description_lines, "Termin", getattr(item, "deadline", None))
    _add_line(description_lines, "Opis", getattr(item, "content", None))
    _add_line(
        description_lines,
        "Nauczyciel",
        _teacher_name(getattr(item, "creator", None)),
    )
    return CalendarEvent(
        summary=summary,
        start=start_date,
        end=end_date,
        description="\n".join(description_lines),
    )


def _teacher_name(teacher) -> str | None:
    if not teacher:
        return None
    return teacher.display_name or f"{teacher.name} {teacher.surname}"


def _add_common_account_lines(lines: list[str], account_info) -> None:
    if not account_info:
        return
    _add_line(lines, "Uczeń", account_info.pupil_name)
    _add_line(lines, "Jednostka", account_info.unit_name)


def _add_line(lines: list[str], label: str, value: object) -> None:
    if value is None or value == "":
        return
    lines.append(f"{label}: {value}")
