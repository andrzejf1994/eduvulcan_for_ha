"""API wrapper for the EduVulcan for HA integration."""

from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from .const import TOKEN_FILE
from .iris_client.api import IrisHebeCeApi
from .iris_client.credentials import RsaCredential

_LOGGER = logging.getLogger(__name__)

PREMIUM_CAPS = "[\"EDUVULCAN_PREMIUM\"]"

_POLISH_TRANSLATION = str.maketrans(
    {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ż": "z",
        "ź": "z",
    }
)


@dataclass(slots=True)
class TokenData:
    """Token data stored in eduvulcan_token.json."""

    jwt: str
    tenant: str
    name: str
    uid: str
    caps: str


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
        self._credential = RsaCredential.create_new("Android", "SM-A525F")
        self._api = IrisHebeCeApi(self._credential)

    async def async_load_token(self) -> TokenData:
        """Load token file and validate premium capabilities."""
        data = await self._async_read_token_file()
        jwt = data.get("jwt")
        tenant = data.get("tenant")
        jwt_payload = data.get("jwt_payload") or {}
        name = jwt_payload.get("name")
        uid = jwt_payload.get("uid")
        caps = jwt_payload.get("caps")
        if not jwt or not tenant:
            raise HomeAssistantError("Token file missing required fields.")
        if not name or not uid:
            raise HomeAssistantError("Token payload missing name or uid.")
        if caps != PREMIUM_CAPS:
            _LOGGER.error("Premium required")
            raise ConfigEntryAuthFailed("Premium required")
        return TokenData(jwt=jwt, tenant=tenant, name=name, uid=uid, caps=caps)

    async def async_get_account_info(self, token: TokenData) -> EduVulcanAccountInfo:
        """Register token and return pupil + unit details."""
        await self._api.register_by_jwt(tokens=[token.jwt], tenant=token.tenant)
        accounts = await self._api.get_accounts()
        if not accounts:
            raise HomeAssistantError("No accounts returned by Iris API.")
        account = accounts[0]
        pupil = account.pupil
        unit = account.unit
        rest_url = unit.rest_url or self._credential.rest_url
        return EduVulcanAccountInfo(
            pupil_id=pupil.id,
            pupil_name=f"{pupil.first_name} {pupil.surname}",
            unit_name=unit.name,
            unit_short=unit.short,
            rest_url=rest_url,
        )

    async def async_get_schedule(
        self, token: TokenData, start_date: date, end_date: date
    ) -> list[object]:
        account = await self.async_get_account_info(token)
        return await self._api.get_schedule(
            rest_url=account.rest_url,
            pupil_id=account.pupil_id,
            date_from=start_date,
            date_to=end_date,
        )

    async def async_get_homework(
        self, token: TokenData, start_date: date, end_date: date
    ) -> list[object]:
        account = await self.async_get_account_info(token)
        return await self._api.get_homework(
            rest_url=account.rest_url,
            pupil_id=account.pupil_id,
            date_from=start_date,
            date_to=end_date,
        )

    async def async_get_exams(
        self, token: TokenData, start_date: date, end_date: date
    ) -> list[object]:
        account = await self.async_get_account_info(token)
        return await self._api.get_exams(
            rest_url=account.rest_url,
            pupil_id=account.pupil_id,
            date_from=start_date,
            date_to=end_date,
        )

    async def async_get_vacations(
        self, token: TokenData, start_date: date, end_date: date
    ) -> list[object]:
        account = await self.async_get_account_info(token)
        if hasattr(self._api, "get_vacations"):
            return await self._api.get_vacations(
                rest_url=account.rest_url,
                pupil_id=account.pupil_id,
                date_from=start_date,
                date_to=end_date,
            )
        http = getattr(self._api, "_http", None)
        if http is None:
            raise HomeAssistantError("Iris API does not support vacations.")
        return await http.request(
            method="GET",
            rest_url=account.rest_url,
            pupil_id=account.pupil_id,
            endpoint="mobile/school/vacation",
            query={
                "pupilId": account.pupil_id,
                "dateFrom": start_date,
                "dateTo": end_date,
            },
        )

    async def async_fetch_all(
        self, start_date: date, end_date: date
    ) -> tuple[dict[str, list[object]], EduVulcanAccountInfo, TokenData]:
        """Fetch lessons, homework, and exams from Iris."""
        token = await self.async_load_token()
        account = await self.async_get_account_info(token)
        lessons = await self._api.get_schedule(
            rest_url=account.rest_url,
            pupil_id=account.pupil_id,
            date_from=start_date,
            date_to=end_date,
        )
        homework = await self._api.get_homework(
            rest_url=account.rest_url,
            pupil_id=account.pupil_id,
            date_from=start_date,
            date_to=end_date,
        )
        exams = await self._api.get_exams(
            rest_url=account.rest_url,
            pupil_id=account.pupil_id,
            date_from=start_date,
            date_to=end_date,
        )
        vacations = await self.async_get_vacations(token, start_date, end_date)
        return {
            "schedule": lessons,
            "homework": homework,
            "exams": exams,
            "vacations": vacations,
        }, account, token

    async def async_close(self) -> None:
        """Close underlying HTTP session."""
        await self._api.async_close()

    async def _async_read_token_file(self) -> dict[str, Any]:
        token_path = Path(self._hass.config.path(TOKEN_FILE))
        if not token_path.exists():
            raise HomeAssistantError("Token file missing.")
        return await self._hass.async_add_executor_job(
            self._read_json_file, token_path
        )

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def slugify_name(name: str) -> str:
    """Normalize name to Home Assistant slug format."""
    normalized = unicodedata.normalize("NFKD", name).lower()
    normalized = normalized.translate(_POLISH_TRANSLATION)
    normalized = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    slug_chars: list[str] = []
    last_was_sep = False
    for char in normalized:
        if char.isalnum():
            slug_chars.append(char)
            last_was_sep = False
        else:
            if not last_was_sep:
                slug_chars.append("_")
                last_was_sep = True
    slug = "".join(slug_chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug
