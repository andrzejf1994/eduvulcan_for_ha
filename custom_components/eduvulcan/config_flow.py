"""Config flow for EduVulcan."""

import json
from pathlib import Path
from typing import Any

from homeassistant import config_entries
import voluptuous as vol

from .api import PREMIUM_CAPS
from .const import DOMAIN, TOKEN_FILE


class EduVulcanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EduVulcan."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors: dict[str, str] = {}
        token_path = Path(self.hass.config.path(TOKEN_FILE))
        if not token_path.exists():
            errors["base"] = "token_missing"
        else:
            try:
                data = await self.hass.async_add_executor_job(
                    self._read_json_file, token_path
                )
            except (OSError, json.JSONDecodeError):
                errors["base"] = "token_invalid"
            else:
                jwt_payload = data.get("jwt_payload") or {}
                uid = jwt_payload.get("uid")
                name = jwt_payload.get("name")
                caps = jwt_payload.get("caps")
                if caps != PREMIUM_CAPS:
                    errors["base"] = "premium_required"
                elif not uid or not name:
                    errors["base"] = "token_invalid"
                else:
                    await self.async_set_unique_id(uid)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=name,
                        data={"uid": uid, "name": name},
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
