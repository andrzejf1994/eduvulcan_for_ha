"""API wrapper for the EduVulcan for HA integration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from iris.api import IrisHebeCeApi
from iris.credentials import RsaCredential

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import TOKEN_FILENAME

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TokenData:
    """Token data stored in eduvulcan_token.json."""

    jwt: str
    tenant: str
    caps: list[str]


@dataclass(slots=True)
class EduVulcanAccountInfo:
    """Account info used for event descriptions."""

    pupil_id: int
    pupil_name: str
    unit_name: str
    unit_short: str
    rest_url: str


class EduVulcanApi:
    """Thin API wrapper around Iris."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def async_fetch_data(
        self, start_date: date, end_date: date
    ) -> tuple[dict[str, Any], EduVulcanAccountInfo]:
        """Fetch lessons, homework, and exams from Iris."""
        token_data = await self._async_load_token_data()
        credential = RsaCredential.create_new("Android", "SM-A525F")
        api = IrisHebeCeApi(credential)
        try:
            await api.register_by_jwt(tokens=[token_data.jwt], tenant=token_data.tenant)
            accounts = await api.get_accounts()
            if not accounts:
                _LOGGER.error("No accounts returned by Iris API.")
                raise ConfigEntryNotReady("No accounts returned by Iris API.")
            account = accounts[0]
            pupil = account.pupil
            unit = account.unit
            rest_url = unit.rest_url or credential.rest_url
            account_info = EduVulcanAccountInfo(
                pupil_id=pupil.id,
                pupil_name=f"{pupil.first_name} {pupil.surname}",
                unit_name=unit.name,
                unit_short=unit.short,
                rest_url=rest_url,
            )
            lessons = await api.get_schedule(
                rest_url=rest_url,
                pupil_id=pupil.id,
                date_from=start_date,
                date_to=end_date,
            )
            homework = await api.get_homework(
                rest_url=rest_url,
                pupil_id=pupil.id,
                date_from=start_date,
                date_to=end_date,
            )
            exams = await api.get_exams(
                rest_url=rest_url,
                pupil_id=pupil.id,
                date_from=start_date,
                date_to=end_date,
            )
            return {
                "lessons": lessons,
                "homework": homework,
                "exams": exams,
            }, account_info
        finally:
            await self._async_close_api(api)

    async def _async_load_token_data(self) -> TokenData:
        config = self._hass.config
        token_path = Path(config.path(TOKEN_FILENAME))
        if not token_path.exists():
            _LOGGER.error("Token file missing at %s", token_path)
            raise ConfigEntryNotReady("Token file missing.")
        data = await self._hass.async_add_executor_job(self._read_json_file, token_path)
        jwt = data.get("jwt")
        tenant = data.get("tenant")
        jwt_payload = data.get("jwt_payload", {})
        caps_raw = jwt_payload.get("caps", [])
        caps = self._normalize_caps(caps_raw)
        if not jwt or not tenant:
            _LOGGER.error("Token file must contain 'jwt' and 'tenant'.")
            raise ConfigEntryNotReady("Token file missing required fields.")
        if "EDUVULCAN_PREMIUM" not in caps:
            _LOGGER.error("Token file missing EDUVULCAN_PREMIUM capability.")
            raise ConfigEntryNotReady(
                "Token file missing EDUVULCAN_PREMIUM capability."
            )
        return TokenData(jwt=jwt, tenant=tenant, caps=caps)

    @staticmethod
    def _normalize_caps(caps_raw: Any) -> list[str]:
        if isinstance(caps_raw, list):
            if not all(isinstance(item, str) for item in caps_raw):
                _LOGGER.error("caps list must contain only strings.")
                raise ConfigEntryNotReady("Invalid caps list.")
            return list(caps_raw)
        if isinstance(caps_raw, str):
            try:
                parsed = json.loads(caps_raw)
            except json.JSONDecodeError:
                return [caps_raw]
            if isinstance(parsed, str):
                return [parsed]
            if isinstance(parsed, list) and all(
                isinstance(item, str) for item in parsed
            ):
                return list(parsed)
            _LOGGER.error("caps string did not parse to a list of strings.")
            raise ConfigEntryNotReady("Invalid caps string format.")
        _LOGGER.error("caps value must be a list or string.")
        raise ConfigEntryNotReady("Invalid caps value.")

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    async def _async_close_api(self, api: IrisHebeCeApi) -> None:
        http_client = getattr(api, "_http", None)
        client = getattr(http_client, "_client", None)
        if client is not None and not client.closed:
            await client.close()
