"""Data update coordinator for EduVulcan for HA."""

from __future__ import annotations

from datetime import date, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import EduVulcanApi, EduVulcanAccountInfo
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class EduVulcanDataUpdateCoordinator(DataUpdateCoordinator[dict[str, list]]):
    """Coordinator to fetch EduVulcan data on a schedule."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=1),
        )
        self.api = EduVulcanApi(hass)
        self.account_info: EduVulcanAccountInfo | None = None

    async def _async_update_data(self) -> dict[str, list]:
        start_date, end_date = _resolve_date_range(date.today())
        data, account_info = await self.api.async_fetch_data(start_date, end_date)
        self.account_info = account_info
        return data


def _resolve_date_range(today: date) -> tuple[date, date]:
    september_first = date(today.year, 9, 1)
    if today < september_first:
        start_date = date(today.year - 1, 9, 1)
    else:
        start_date = september_first
    return start_date, today
