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
        try:
            token = await self.api.async_load_token()
            accounts = await self.api.async_get_accounts(token)
            if not accounts:
                raise UpdateFailed("No accounts returned by Iris API.")
            account = accounts[0]
            period = next(
                (period for period in (account.periods or []) if period.current),
                None,
            )
            if period:
                start_date, end_date = period.date_from, period.date_to
                _LOGGER.debug(
                    "Using current period date range: %s - %s",
                    start_date,
                    end_date,
                )
            else:
                start_date, end_date = _resolve_date_range(date.today())
                _LOGGER.debug(
                    "Using fallback school year date range: %s - %s",
                    start_date,
                    end_date,
                )
            account_info = self.api.build_account_info(account)
            data = await self.api.async_fetch_all_for_account(
                account_info, start_date, end_date
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
    return _get_school_year_start_date(today), _get_school_year_end_date(today)


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
