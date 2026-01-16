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
        account_info = self.coordinator.account_info
        if isinstance(item, dict):
            return _build_generic_event(item, self._definition.all_day, tz)
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


def _format_time(value: time) -> str:
    return value.strftime("%H:%M")


def _format_time_range(
    start_time: time | None,
    end_time: time | None,
    display: object | None,
) -> str | None:
    if start_time and end_time:
        return f"{_format_time(start_time)}-{_format_time(end_time)}"
    if display:
        return str(display)
    return None


def _build_lesson_event(item: object, account_info, tz) -> CalendarEvent | None:
    subject_name = _get_nested_value(item, "subject", "name")
    room_code = _get_nested_value(item, "room", "code")
    time_slot = _get_value(item, "time_slot", "timeSlot")
    start_time = _get_value(time_slot, "start")
    end_time = _get_value(time_slot, "end")
    if not time_slot or not start_time or not end_time:
        return None
    summary = subject_name or _get_value(item, "event") or "Lekcja"
    date_value = _get_value(item, "date_", "date", "dateAt")
    if not date_value:
        return None
    start_dt = datetime.combine(date_value, start_time, tzinfo=tz)
    end_dt = datetime.combine(date_value, end_time, tzinfo=tz)
    description = _build_event_description(KIND_SCHEDULE, item, account_info)
    return CalendarEvent(
        summary=summary,
        start=start_dt,
        end=end_dt,
        description=description,
        location=room_code,
    )


def _build_homework_event(item: object, account_info) -> CalendarEvent:
    subject_name = _get_nested_value(item, "subject", "name")
    summary = f"{subject_name} – Zadanie" if subject_name else "Zadanie"
    deadline = _get_value(item, "deadline", "deadlineAt") or _get_value(
        item, "date_", "date", "dateAt"
    )
    start_date = deadline.date() if isinstance(deadline, datetime) else deadline
    if not start_date:
        start_date = date.today()
    end_date = start_date + timedelta(days=1)
    description = _build_event_description(KIND_HOMEWORK, item, account_info)
    return CalendarEvent(
        summary=summary,
        start=start_date,
        end=end_date,
        description=description,
    )


def _build_exam_event(item: object, account_info) -> CalendarEvent:
    subject_name = _get_nested_value(item, "subject", "name")
    summary = f"{subject_name} – Sprawdzian" if subject_name else "Sprawdzian"
    deadline = _get_value(item, "deadline", "deadlineAt")
    start_date = deadline.date() if isinstance(deadline, datetime) else deadline
    if not start_date:
        start_date = date.today()
    end_date = start_date + timedelta(days=1)
    description = _build_event_description(KIND_EXAMS, item, account_info)
    return CalendarEvent(
        summary=summary,
        start=start_date,
        end=end_date,
        description=description,
    )


def _build_event_description(
    kind: str,
    item: object,
    account_info,
) -> str | None:
    lines: list[str] = []
    _add_common_account_lines(lines, account_info)
    if kind == KIND_SCHEDULE:
        _add_schedule_description(lines, item)
    elif kind == KIND_HOMEWORK:
        _add_homework_description(lines, item)
    elif kind == KIND_EXAMS:
        _add_exam_description(lines, item)
    return "\n".join(lines) if lines else None


def _add_schedule_description(lines: list[str], item: object) -> None:
    subject_name = _get_nested_value(item, "subject", "name")
    room_code = _get_nested_value(item, "room", "code")
    time_slot = _get_value(item, "time_slot", "timeSlot")
    start_time = _get_value(time_slot, "start")
    end_time = _get_value(time_slot, "end")
    _add_line(lines, "Przedmiot", subject_name)
    _add_line(
        lines,
        "Nauczyciel",
        _teacher_name(_get_value(item, "teacher_primary", "teacherPrimary")),
    )
    _add_line(
        lines,
        "Nauczyciel dodatkowy",
        _teacher_name(_get_value(item, "teacher_secondary", "teacherSecondary")),
    )
    _add_line(
        lines,
        "Nauczyciel dodatkowy 2",
        _teacher_name(_get_value(item, "teacher_secondary2", "teacherSecondary2")),
    )
    _add_line(lines, "Sala", room_code)
    _add_line(lines, "Klasa", _get_nested_value(item, "clazz", "symbol"))
    _add_line(
        lines,
        "Grupa",
        _get_nested_value(item, "distribution", "shortcut")
        or _get_nested_value(item, "distribution", "name"),
    )
    _add_line(
        lines,
        "Typ lekcji",
        _get_nested_value(item, "distribution", "part_type")
        or _get_nested_value(item, "distribution", "partType"),
    )
    _add_line(
        lines,
        "Godziny",
        _format_time_range(
            start_time,
            end_time,
            _get_value(time_slot, "display"),
        ),
    )
    _add_line(lines, "Numer lekcji", _get_value(time_slot, "position"))
    _add_line(lines, "Uwagi", _get_value(item, "event"))
    _add_line(lines, "Alias ucznia", _get_value(item, "pupil_alias", "pupilAlias"))
    _add_line(lines, "Rodzic", _get_value(item, "parent"))


def _add_homework_description(lines: list[str], item: object) -> None:
    _add_line(lines, "Przedmiot", _get_nested_value(item, "subject", "name"))
    _add_line(lines, "Treść", _get_value(item, "content", "description"))
    _add_line(lines, "Nauczyciel", _teacher_name(_get_value(item, "creator")))
    _add_line(lines, "Termin", _get_value(item, "deadline", "deadlineAt"))
    _add_line(lines, "Data lekcji", _get_value(item, "date_", "date", "dateAt"))
    _add_line(lines, "Utworzono", _get_value(item, "created_at", "createdAt"))
    _add_line(lines, "Zmieniono", _get_value(item, "modified_at", "modifiedAt"))
    _add_line(
        lines,
        "Wymaga odpowiedzi",
        _get_value(item, "is_answer_required", "isAnswerRequired"),
    )
    _add_line(lines, "Odpowiedź do", _get_value(item, "answer_at", "answerAt"))
    attachments = _get_value(item, "attachments") or []
    if attachments:
        attachment_names = ", ".join(
            str(_get_value(attachment, "name") or attachment)
            for attachment in attachments
        )
        _add_line(lines, "Załączniki", attachment_names)
        attachment_links = ", ".join(
            str(_get_value(attachment, "link"))
            for attachment in attachments
            if _get_value(attachment, "link")
        )
        _add_line(lines, "Linki", attachment_links)
    _add_line(lines, "Metadane", _get_value(item, "didactics"))


def _add_exam_description(lines: list[str], item: object) -> None:
    _add_line(lines, "Przedmiot", _get_nested_value(item, "subject", "name"))
    _add_line(lines, "Rodzaj", _get_value(item, "type"))
    _add_line(lines, "Opis", _get_value(item, "content", "description"))
    _add_line(lines, "Nauczyciel", _teacher_name(_get_value(item, "creator")))
    _add_line(lines, "Termin", _get_value(item, "deadline", "deadlineAt"))
    _add_line(lines, "Utworzono", _get_value(item, "created_at", "createdAt"))
    _add_line(lines, "Zmieniono", _get_value(item, "modified_at", "modifiedAt"))
    _add_line(lines, "Id typu", _get_value(item, "type_id", "typeId"))
    _add_line(lines, "Metadane", _get_value(item, "didactics"))


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
