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

from .const import (
    CALENDAR_EXAMS,
    CALENDAR_HOMEWORK,
    CALENDAR_LESSONS,
    DOMAIN,
)
from .coordinator import EduVulcanDataUpdateCoordinator


@dataclass(frozen=True)
class CalendarDefinition:
    """Definition for a calendar entity."""

    name: str
    key: str
    all_day: bool


CALENDARS: tuple[CalendarDefinition, ...] = (
    CalendarDefinition(
        name="Plan Lekcji",
        key=CALENDAR_LESSONS,
        all_day=False,
    ),
    CalendarDefinition(
        name="Zadania Domowe",
        key=CALENDAR_HOMEWORK,
        all_day=True,
    ),
    CalendarDefinition(
        name="Egzaminy / Sprawdziany",
        key=CALENDAR_EXAMS,
        all_day=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EduVulcan calendar entities."""
    coordinator: EduVulcanDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EduVulcanCalendarEntity(coordinator, entry.entry_id, calendar)
        for calendar in CALENDARS
    ]
    async_add_entities(entities)


class EduVulcanCalendarEntity(CoordinatorEntity, CalendarEntity):
    """Representation of an EduVulcan calendar."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: EduVulcanDataUpdateCoordinator,
        entry_id: str,
        definition: CalendarDefinition,
    ) -> None:
        super().__init__(coordinator)
        self._definition = definition
        self._attr_name = definition.name
        self._attr_unique_id = f"{entry_id}_{definition.key}"

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        data = self.coordinator.data or {}
        items = data.get(self._definition.key, [])
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
        if self._definition.key == CALENDAR_LESSONS:
            return _build_lesson_event(item, account_info, tz)
        if self._definition.key == CALENDAR_HOMEWORK:
            return _build_homework_event(item, account_info)
        if self._definition.key == CALENDAR_EXAMS:
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


def _build_lesson_event(item: object, account_info, tz) -> CalendarEvent:
    subject_name = None
    if getattr(item, "subject", None):
        subject_name = item.subject.name
    summary = subject_name or item.event or "Lekcja"
    start_dt = datetime.combine(item.date_, item.time_slot.start, tzinfo=tz)
    end_dt = datetime.combine(item.date_, item.time_slot.end, tzinfo=tz)
    description_lines = ["Typ: Lesson"]
    _add_common_account_lines(description_lines, account_info)
    _add_line(description_lines, "ScheduleId", getattr(item, "id", None))
    _add_line(description_lines, "MergeChangeId", getattr(item, "merge_change_id", None))
    _add_line(description_lines, "Event", getattr(item, "event", None))
    _add_line(description_lines, "Date", getattr(item, "date_", None))
    _add_line(description_lines, "TimeSlot", getattr(item.time_slot, "display", None))
    _add_line(description_lines, "TimeSlotId", getattr(item.time_slot, "id", None))
    _add_line(description_lines, "Subject", subject_name)
    if getattr(item, "subject", None):
        _add_line(description_lines, "SubjectId", item.subject.id)
        _add_line(description_lines, "SubjectKey", item.subject.key)
        _add_line(description_lines, "SubjectCode", item.subject.code)
    _add_line(
        description_lines, "Room", getattr(getattr(item, "room", None), "code", None)
    )
    _add_line(
        description_lines, "RoomId", getattr(getattr(item, "room", None), "id", None)
    )
    _add_line(
        description_lines,
        "Class",
        getattr(getattr(item, "clazz", None), "display", None),
    )
    _add_line(
        description_lines, "ClassId", getattr(getattr(item, "clazz", None), "id", None)
    )
    _add_line(
        description_lines,
        "TeacherPrimary",
        _teacher_name(getattr(item, "teacher_primary", None)),
    )
    _add_line(
        description_lines,
        "TeacherPrimaryId",
        getattr(getattr(item, "teacher_primary", None), "id", None),
    )
    _add_line(
        description_lines,
        "TeacherSecondary",
        _teacher_name(getattr(item, "teacher_secondary", None)),
    )
    _add_line(
        description_lines,
        "TeacherSecondaryId",
        getattr(getattr(item, "teacher_secondary", None), "id", None),
    )
    _add_line(
        description_lines,
        "TeacherSecondary2",
        _teacher_name(getattr(item, "teacher_secondary2", None)),
    )
    _add_line(
        description_lines,
        "TeacherSecondary2Id",
        getattr(getattr(item, "teacher_secondary2", None), "id", None),
    )
    _add_line(
        description_lines,
        "DistributionId",
        getattr(getattr(item, "distribution", None), "id", None),
    )
    _add_line(description_lines, "PupilAlias", getattr(item, "pupil_alias", None))
    _add_line(description_lines, "Parent", getattr(item, "parent", None))
    return CalendarEvent(
        summary=summary,
        start=start_dt,
        end=end_dt,
        description="\n".join(description_lines),
    )


def _build_homework_event(item: object, account_info) -> CalendarEvent:
    subject_name = item.subject.name if getattr(item, "subject", None) else None
    summary = subject_name or "Zadanie domowe"
    deadline = getattr(item, "deadline", None) or getattr(item, "date_", None)
    start_date = deadline.date() if isinstance(deadline, datetime) else deadline
    end_date = start_date + timedelta(days=1)
    description_lines = ["Typ: Homework"]
    _add_common_account_lines(description_lines, account_info)
    _add_line(description_lines, "HomeworkId", getattr(item, "id", None))
    _add_line(description_lines, "HomeworkKey", getattr(item, "key", None))
    _add_line(description_lines, "IdHomework", getattr(item, "id_homework", None))
    _add_line(description_lines, "IdPupil", getattr(item, "id_pupil", None))
    _add_line(description_lines, "Subject", subject_name)
    if getattr(item, "subject", None):
        _add_line(description_lines, "SubjectId", item.subject.id)
        _add_line(description_lines, "SubjectKey", item.subject.key)
        _add_line(description_lines, "SubjectCode", item.subject.code)
    _add_line(description_lines, "Content", getattr(item, "content", None))
    _add_line(
        description_lines, "IsAnswerRequired", getattr(item, "is_answer_required", None)
    )
    _add_line(description_lines, "Date", getattr(item, "date_", None))
    _add_line(description_lines, "Deadline", getattr(item, "deadline", None))
    _add_line(description_lines, "CreatedAt", getattr(item, "created_at", None))
    _add_line(description_lines, "ModifiedAt", getattr(item, "modified_at", None))
    _add_line(description_lines, "AnswerAt", getattr(item, "answer_at", None))
    _add_line(
        description_lines, "Creator", _teacher_name(getattr(item, "creator", None))
    )
    _add_line(
        description_lines,
        "CreatorId",
        getattr(getattr(item, "creator", None), "id", None),
    )
    attachments = getattr(item, "attachments", [])
    if attachments:
        _add_line(description_lines, "Attachments", ", ".join(a.name for a in attachments))
        _add_line(
            description_lines,
            "AttachmentLinks",
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
    summary = subject_name or "Egzamin"
    deadline = getattr(item, "deadline", None)
    start_date = deadline.date() if isinstance(deadline, datetime) else deadline
    end_date = start_date + timedelta(days=1)
    description_lines = ["Typ: Exam"]
    _add_common_account_lines(description_lines, account_info)
    _add_line(description_lines, "ExamId", getattr(item, "id", None))
    _add_line(description_lines, "ExamKey", getattr(item, "key", None))
    _add_line(description_lines, "ExamType", getattr(item, "type", None))
    _add_line(description_lines, "ExamTypeId", getattr(item, "type_id", None))
    _add_line(description_lines, "PupilId", getattr(item, "pupil_id", None))
    _add_line(description_lines, "Subject", subject_name)
    if getattr(item, "subject", None):
        _add_line(description_lines, "SubjectId", item.subject.id)
        _add_line(description_lines, "SubjectKey", item.subject.key)
        _add_line(description_lines, "SubjectCode", item.subject.code)
    _add_line(description_lines, "Content", getattr(item, "content", None))
    _add_line(description_lines, "Deadline", getattr(item, "deadline", None))
    _add_line(description_lines, "CreatedAt", getattr(item, "created_at", None))
    _add_line(description_lines, "ModifiedAt", getattr(item, "modified_at", None))
    _add_line(
        description_lines, "Creator", _teacher_name(getattr(item, "creator", None))
    )
    _add_line(
        description_lines,
        "CreatorId",
        getattr(getattr(item, "creator", None), "id", None),
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
    _add_line(lines, "PupilId", account_info.pupil_id)
    _add_line(lines, "PupilName", account_info.pupil_name)
    _add_line(lines, "UnitName", account_info.unit_name)
    _add_line(lines, "UnitShort", account_info.unit_short)
    _add_line(lines, "RestURL", account_info.rest_url)


def _add_line(lines: list[str], label: str, value: object) -> None:
    if value is None or value == "":
        return
    lines.append(f"{label}: {value}")
