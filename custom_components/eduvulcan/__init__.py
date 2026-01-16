"""EduVulcan integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from .api import EduVulcanApi
from .const import DOMAIN, PLATFORMS
from .coordinator import EduVulcanCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EduVulcan from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    api = EduVulcanApi(hass)
    try:
        await api.async_load_token()
    except ConfigEntryAuthFailed:
        _LOGGER.error("Premium required")
        raise
    except HomeAssistantError as err:
        raise HomeAssistantError(str(err)) from err
    coordinator = EduVulcanCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if data and "api" in data:
            await data["api"].async_close()
    return unload_ok
