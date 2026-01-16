"""Config flow for EduVulcan."""

from homeassistant import config_entries

from .const import DOMAIN


class EduVulcanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EduVulcan."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        return self.async_create_entry(title="EduVulcan", data={})
