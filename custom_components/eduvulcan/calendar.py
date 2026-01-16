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

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        data = self.coordinator.data or {}
        items = data.get(self._definition.kind, [])
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        now = dt_util.utcnow()
        upcoming: list[CalendarEvent] = []
        for item in items:
            event = self._build_event(item, tz)
            if event is None:
                continue
            if _normalize_event_datetime(event.end, tz) >= now:
                upcoming.append(event)
        if not upcoming:
            return None
        return min(
            upcoming,
            key=lambda candidate: _normalize_event_datetime(candidate.start, tz),
        )

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
        if isinstance(item, dict):
            return _build_generic_event(item, self._definition.all_day, tz)
        if self._definition.kind == KIND_SCHEDULE:
            return _build_lesson_event(item, tz)
        if self._definition.kind == KIND_HOMEWORK:
            return _build_homework_event(item)
        if self._definition.kind == KIND_EXAMS:
            return _build_exam_event(item)
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


def _build_lesson_event(item: object, tz) -> CalendarEvent | None:
    if _is_cancelled_lesson(item):
        # Skip cancelled lessons – do not create calendar events
        return None
    subject_name = _get_nested_value(item, "subject", "name")
    room_code = _get_nested_value(item, "room", "code")
    time_slot = _get_value(item, "time_slot", "timeSlot")
    start_time = _get_value(time_slot, "start")
    end_time = _get_value(time_slot, "end")
    if not time_slot or not start_time or not end_time:
        return None
    summary = subject_name or _get_value(item, "event") or "Lekcja"
    if _is_substitution_lesson(item):
        summary = f"{summary} (Zastępstwo)"
    date_value = _resolve_lesson_date(item)
    if not date_value:
        return None
    start_dt = datetime.combine(date_value, start_time, tzinfo=tz)
    end_dt = datetime.combine(date_value, end_time, tzinfo=tz)
    description = _build_event_description(KIND_SCHEDULE, item)
    location = f"Sala {room_code}" if room_code else None
    return CalendarEvent(
        summary=summary,
        start=start_dt,
        end=end_dt,
        description=description,
        location=location,
    )


def _resolve_lesson_date(item: object) -> date | None:
    date_value = _get_value(item, "date_", "date", "dateAt", "DateAt")
    if isinstance(date_value, datetime):
        date_value = date_value.date()
    weekday_value = _get_value(
        item,
        "day",
        "weekday",
        "day_of_week",
        "dayOfWeek",
    )
    week_start = _get_value(
        item,
        "week_start",
        "weekStart",
        "week_start_date",
        "weekStartDate",
    )
    if isinstance(week_start, datetime):
        week_start = week_start.date()
    normalized_weekday = (
        _normalize_weekday_value(weekday_value)
        if isinstance(weekday_value, int)
        else None
    )
    if date_value is None and isinstance(week_start, date) and normalized_weekday:
        # BUGFIX: schedule events were not created on Mondays due to incorrect weekday mapping
        return week_start + timedelta(days=normalized_weekday - 1)
    if isinstance(date_value, date) and normalized_weekday:
        if normalized_weekday != date_value.isoweekday():
            # BUGFIX: schedule events were not created on Mondays due to incorrect weekday mapping
            return date_value + timedelta(
                days=normalized_weekday - date_value.isoweekday()
            )
    return date_value


def _normalize_weekday_value(value: int) -> int | None:
    if 1 <= value <= 7:
        return value
    if 0 <= value <= 6:
        return value + 1
    return None


def _is_cancelled_lesson(item: object) -> bool:
    if _get_value(
        item,
        "cancelled",
        "canceled",
        "is_cancelled",
        "is_canceled",
        "isCancelled",
        "isCanceled",
    ):
        return True
    status = _get_value(item, "status")
    return isinstance(status, str) and status.upper() == "CANCELLED"


def _is_substitution_lesson(item: object) -> bool:
    if _get_value(
        item,
        "substitution",
        "is_substitution",
        "isSubstitution",
        "replacement",
        "is_replacement",
        "isReplacement",
    ):
        return True
    status = _get_value(item, "status")
    return isinstance(status, str) and status.upper() in {"SUBSTITUTION", "REPLACEMENT"}


def _build_homework_event(item: object) -> CalendarEvent:
    subject_name = _get_nested_value(item, "subject", "name")
    summary = f"{subject_name} – Zadanie" if subject_name else "Zadanie"
    deadline = _get_value(item, "deadline", "deadlineAt") or _get_value(
        item, "date_", "date", "dateAt"
    )
    start_date = deadline.date() if isinstance(deadline, datetime) else deadline
    if not start_date:
        start_date = date.today()
    end_date = start_date + timedelta(days=1)
    description = _build_event_description(KIND_HOMEWORK, item)
    return CalendarEvent(
        summary=summary,
        start=start_date,
        end=end_date,
        description=description,
    )


def _build_exam_event(item: object) -> CalendarEvent:
    subject_name = _get_nested_value(item, "subject", "name")
    summary = f"{subject_name} – Sprawdzian" if subject_name else "Sprawdzian"
    deadline = _get_value(item, "deadline", "deadlineAt")
    start_date = deadline.date() if isinstance(deadline, datetime) else deadline
    if not start_date:
        start_date = date.today()
    end_date = start_date + timedelta(days=1)
    description = _build_event_description(KIND_EXAMS, item)
    return CalendarEvent(
        summary=summary,
        start=start_date,
        end=end_date,
        description=description,
    )


def _build_event_description(kind: str, item: object) -> str | None:
    lines: list[str] = []
    if kind == KIND_SCHEDULE:
        _add_schedule_description(lines, item)
    elif kind == KIND_HOMEWORK:
        _add_homework_description(lines, item)
    elif kind == KIND_EXAMS:
        _add_exam_description(lines, item)
    return "\n".join(lines) if lines else None


def _add_schedule_description(lines: list[str], item: object) -> None:
    teachers = [
        _teacher_name(_get_value(item, "teacher_primary", "teacherPrimary")),
        _teacher_name(_get_value(item, "teacher_secondary", "teacherSecondary")),
        _teacher_name(_get_value(item, "teacher_secondary2", "teacherSecondary2")),
    ]
    teacher_names = [teacher for teacher in teachers if teacher]
    if not teacher_names:
        return
    label = "Nauczyciele" if len(teacher_names) > 1 else "Nauczyciel"
    _add_line(lines, label, ", ".join(teacher_names))


def _add_homework_description(lines: list[str], item: object) -> None:
    _add_line(lines, "Przedmiot", _get_nested_value(item, "subject", "name"))
    _add_line(lines, "Treść", _get_value(item, "content", "description"))
    _add_line(lines, "Utworzono", _get_value(item, "created_at", "createdAt"))
    _add_line(lines, "Zmieniono", _get_value(item, "modified_at", "modifiedAt"))


def _add_exam_description(lines: list[str], item: object) -> None:
    _add_line(lines, "Rodzaj", _get_value(item, "type"))
    _add_line(lines, "Opis", _get_value(item, "content", "description"))
    _add_line(lines, "Nauczyciel", _teacher_name(_get_value(item, "creator")))
    _add_line(lines, "Utworzono", _get_value(item, "created_at", "createdAt"))
    _add_line(lines, "Zmieniono", _get_value(item, "modified_at", "modifiedAt"))


def _teacher_name(teacher) -> str | None:
    if not teacher:
        return None
    return teacher.display_name or f"{teacher.name} {teacher.surname}"


def _add_line(lines: list[str], label: str, value: object) -> None:
    if value is None or value == "":
        return
    lines.append(f"{label}: {value}")


def _build_generic_event(
    item: dict[str, object],
    all_day: bool,
    tz,
) -> CalendarEvent | None:
    summary = (
        _get_value(item, "summary", "title", "subject", "name") or "Wydarzenie"
    )
    description = _get_value(item, "description", "content", "details")
    start_value = _get_value(
        item,
        "start",
        "start_date",
        "start_datetime",
        "date",
        "date_",
        "dateAt",
    )
    end_value = _get_value(item, "end", "end_date", "end_datetime")
    start = _coerce_event_datetime(start_value, all_day, tz)
    if start is None:
        return None
    end = _coerce_event_datetime(end_value, all_day, tz)
    if end is None:
        end = (
            start + timedelta(days=1)
            if all_day
            else start + timedelta(hours=1)
        )
    return CalendarEvent(
        summary=str(summary),
        start=start,
        end=end,
        description=str(description) if description else None,
    )


def _coerce_event_datetime(
    value: object,
    all_day: bool,
    tz,
) -> datetime | date | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.date() if all_day else value
    if isinstance(value, date):
        return value if all_day else datetime.combine(value, time.min, tzinfo=tz)
    return None


def _get_value(item: object, *keys: str) -> object | None:
    for key in keys:
        if isinstance(item, dict):
            if key in item:
                return item[key]
        elif hasattr(item, key):
            return getattr(item, key)
    return None


def _get_nested_value(item: object, *keys: str) -> object | None:
    current: object | None = item
    for key in keys:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
    return current
