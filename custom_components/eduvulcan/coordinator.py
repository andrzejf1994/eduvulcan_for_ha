"""Data update coordinator for EduVulcan for HA."""

from __future__ import annotations

from datetime import date, datetime
from collections import Counter
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EduVulcanApi, EduVulcanAccountInfo, slugify_name
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class EduVulcanCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Coordinator to fetch EduVulcan data on a schedule."""

    def __init__(self, hass: HomeAssistant, api: EduVulcanApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.account_info: EduVulcanAccountInfo | None = None
        self.last_error: str | None = None

    async def _async_update_data(self) -> dict[str, object]:
        start_date, end_date = _resolve_date_range(date.today())
        try:
            data, account_info, token = await self.api.async_fetch_all(
                start_date, end_date
            )
        except Exception as err:  # noqa: BLE001 - surface update failure only
            self.last_error = str(err)
            _LOGGER.error("Failed to update EduVulcan data: %s", err)
            raise UpdateFailed(str(err)) from err
        self.last_error = None
        self.account_info = account_info
        self._log_schedule_distribution(data.get("schedule", []))
        return {
            **data,
            "name": token.name,
            "slug": slugify_name(token.name),
            "uid": token.uid,
        }

    def _log_schedule_distribution(self, lessons: list[object]) -> None:
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        weekday_counts: Counter[int] = Counter()
        invalid_dates = 0
        for item in lessons:
            date_value = _get_value(item, "date_", "date", "dateAt", "DateAt")
            date_only = _coerce_date_value(date_value)
            if not date_only:
                invalid_dates += 1
                continue
            weekday_counts[date_only.isoweekday()] += 1
        _LOGGER.debug(
            "Schedule items=%s weekday_counts=%s invalid_dates=%s",
            len(lessons),
            dict(weekday_counts),
            invalid_dates,
        )
        counts_ordered = {
            "mon": weekday_counts.get(1, 0),
            "tue": weekday_counts.get(2, 0),
            "wed": weekday_counts.get(3, 0),
            "thu": weekday_counts.get(4, 0),
            "fri": weekday_counts.get(5, 0),
            "sat": weekday_counts.get(6, 0),
            "sun": weekday_counts.get(7, 0),
        }
        _LOGGER.warning(
            "Schedule diagnostic: items=%s weekdays=%s invalid_dates=%s",
            len(lessons),
            counts_ordered,
            invalid_dates,
        )


def _resolve_date_range(today: date) -> tuple[date, date]:
    return _get_school_year_start_date(today), _get_school_year_end_date(today)


def _get_value(item: object, *keys: str) -> object | None:
    for key in keys:
        if isinstance(item, dict):
            if key in item:
                return item[key]
        elif hasattr(item, key):
            return getattr(item, key)
    return None


def _coerce_date_value(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _get_school_year_start_date(today: date) -> date:
    end_of_august = date(today.year, 8, 31)
    if today <= end_of_august:
        return date(today.year - 1, 9, 1)
    return date(today.year, 9, 1)


def _get_school_year_end_date(today: date) -> date:
    end_of_august = date(today.year, 8, 31)
    if today <= end_of_august:
        return end_of_august
    return date(today.year + 1, 8, 31)
