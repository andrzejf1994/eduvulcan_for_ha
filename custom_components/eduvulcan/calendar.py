"""Calendar entities for EduVulcan for HA."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, KIND_EXAMS, KIND_HOMEWORK, KIND_SCHEDULE
from .coordinator import EduVulcanCoordinator

_LOGGER = logging.getLogger(__name__)


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
        items = _collect_calendar_items(data, self._definition.kind)
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
        items = _collect_calendar_items(data, self._definition.kind)
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
            if self._definition.kind == KIND_SCHEDULE:
                if _is_vacation_item(item):
                    return _build_vacation_event(item)
                return _build_lesson_event(item, tz)
            return _build_generic_event(item, self._definition.all_day, tz)
        if self._definition.kind == KIND_SCHEDULE:
            if _is_vacation_item(item):
                return _build_vacation_event(item)
            return _build_lesson_event(item, tz)
        if self._definition.kind == KIND_HOMEWORK:
            return _build_homework_event(item)
        if self._definition.kind == KIND_EXAMS:
            return _build_exam_event(item)
        return None


def _collect_calendar_items(data: dict, kind: str) -> list[object]:
    items = list(data.get(kind, []) or [])
    if kind == KIND_SCHEDULE:
        items.extend(data.get("vacations", []) or [])
    return items


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
    substitution = _get_value(item, "substitution", "Substitution")
    subject_name = _get_nested_value(item, "subject", "name") or _get_nested_value(
        item, "Subject", "Name"
    )
    substitution_subject = _get_nested_value(
        substitution, "subject", "name"
    ) or _get_nested_value(substitution, "Subject", "Name")
    if substitution_subject:
        subject_name = substitution_subject
    room_code = (
        _get_nested_value(substitution, "room", "code")
        or _get_nested_value(substitution, "Room", "Code")
        or _get_nested_value(item, "room", "code")
        or _get_nested_value(item, "Room", "Code")
    )
    time_slot = _get_value(item, "time_slot", "timeSlot", "TimeSlot")
    start_time = _coerce_time_value(_get_value(time_slot, "start", "Start"))
    end_time = _coerce_time_value(_get_value(time_slot, "end", "End"))
    if not time_slot or not start_time or not end_time:
        _LOGGER.debug(
            "Skipping lesson without time slot: time_slot=%s start=%s end=%s item=%s",
            time_slot,
            start_time,
            end_time,
            item,
        )
        return None
    summary = subject_name or _get_value(item, "event", "Event") or "Lekcja"
    if _is_substitution_lesson(item):
        summary = f"{summary} (Zastępstwo)"
    date_value = _resolve_lesson_date(item)
    if not date_value:
        _LOGGER.debug("Skipping lesson without date: item=%s", item)
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


def _is_vacation_item(item: object) -> bool:
    name = _get_value(item, "name", "Name")
    date_from = _get_value(item, "date_from", "dateFrom", "From")
    date_to = _get_value(item, "date_to", "dateTo", "To")
    return bool(name and date_from and date_to)


def _build_vacation_event(item: object) -> CalendarEvent | None:
    name = _get_value(item, "name", "Name") or "Dzien wolny"
    date_from = _get_value(item, "date_from", "dateFrom", "From")
    date_to = _get_value(item, "date_to", "dateTo", "To")
    if isinstance(date_from, datetime):
        start_date = date_from.date()
    elif isinstance(date_from, str):
        start_date = _coerce_date_value(date_from)
    else:
        start_date = date_from
    if isinstance(date_to, datetime):
        end_date = date_to.date()
    elif isinstance(date_to, str):
        end_date = _coerce_date_value(date_to)
    else:
        end_date = date_to
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        return None
    return CalendarEvent(
        summary=str(name),
        start=start_date,
        end=end_date + timedelta(days=1),
    )


def _resolve_lesson_date(item: object) -> date | None:
    date_value = _get_value(item, "date_", "date", "dateAt", "DateAt")
    if isinstance(date_value, datetime):
        return date_value.date()
    if isinstance(date_value, date):
        return date_value
    if isinstance(date_value, str):
        parsed_date = _coerce_date_value(date_value)
        if parsed_date:
            return parsed_date
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
    normalized_weekday = _normalize_weekday_value(weekday_value)
    if isinstance(week_start, date) and normalized_weekday:
        return week_start + timedelta(days=normalized_weekday - 1)
    return None


def _normalize_weekday_value(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip().isdigit():
            return None
        value = int(value)
    if 1 <= value <= 7:
        return value
    if 0 <= value <= 6:
        return value + 1
    return None


def _is_cancelled_lesson(item: object) -> bool:
    substitution = _get_value(item, "substitution", "Substitution")
    change_type = _get_nested_value(substitution, "change", "type") or _get_nested_value(
        substitution, "Change", "Type"
    )
    if change_type in {0, 1, 4}:
        return True
    if _get_value(
        substitution, "class_absence", "classAbsence", "ClassAbsence"
    ) is True:
        return True
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
    substitution = _get_value(item, "substitution", "Substitution")
    if substitution:
        return True
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
    substitution = _get_value(item, "substitution", "Substitution")
    teacher_source = substitution if substitution else item
    teachers = [
        _teacher_name(
            _get_value(
                teacher_source, "teacher_primary", "teacherPrimary", "TeacherPrimary"
            )
        ),
        _teacher_name(
            _get_value(
                teacher_source,
                "teacher_secondary",
                "teacherSecondary",
                "TeacherSecondary",
            )
        ),
        _teacher_name(
            _get_value(
                teacher_source,
                "teacher_secondary2",
                "teacherSecondary2",
                "TeacherSecondary2",
            )
        ),
    ]
    _add_line(
        lines,
        "Powód nieobecności",
        _get_nested_value(substitution, "teacher_absence_effect_name")
        or _get_nested_value(substitution, "TeacherAbsenceEffectName")
        or _get_nested_value(item, "teacher_absence_effect_name")
        or _get_nested_value(item, "TeacherAbsenceEffectName"),
    )
    _add_line(
        lines,
        "Powód",
        _get_nested_value(substitution, "reason")
        or _get_nested_value(substitution, "Reason")
        or _get_nested_value(item, "reason")
        or _get_nested_value(item, "Reason"),
    )
    teacher_names = [teacher for teacher in teachers if teacher]
    if not teacher_names:
        return
    label = "Nauczyciele" if len(teacher_names) > 1 else "Nauczyciel"
    _add_line(lines, label, ", ".join(teacher_names))


def _add_homework_description(lines: list[str], item: object) -> None:
    content = _get_value(item, "content", "description")
    if content:
        lines.append(str(content))


def _add_exam_description(lines: list[str], item: object) -> None:
    content = _get_value(item, "content", "description")
    if content:
        lines.append(str(content))


def _teacher_name(teacher) -> str | None:
    if not teacher:
        return None
    if isinstance(teacher, dict):
        display_name = (
            teacher.get("display_name")
            or teacher.get("displayName")
            or teacher.get("DisplayName")
        )
        if display_name:
            return display_name
        name = teacher.get("name") or teacher.get("Name") or ""
        surname = teacher.get("surname") or teacher.get("Surname") or ""
        full = f"{name} {surname}".strip()
        return full if full else None
    return teacher.display_name or f"{teacher.name} {teacher.surname}"


def _coerce_time_value(value: object) -> time | None:
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, str):
        try:
            return time.fromisoformat(value)
        except ValueError:
            return None
    return None


def _coerce_date_value(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


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
