"""Data update coordinator for EduVulcan for HA."""

from __future__ import annotations

from datetime import date
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
        return {
            **data,
            "name": token.name,
            "slug": slugify_name(token.name),
            "uid": token.uid,
        }


def _resolve_date_range(today: date) -> tuple[date, date]:
    september_first = date(today.year, 9, 1)
    if today < september_first:
        start_date = date(today.year - 1, 9, 1)
    else:
        start_date = september_first
    return start_date, today
