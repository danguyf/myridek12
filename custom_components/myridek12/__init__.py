"""The My Ride K-12 integration."""
from __future__ import annotations

import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import MyRideK12Api, MyRideK12ApiError, MyRideK12AuthError
from .const import (
    CONF_END_HOUR,
    CONF_START_HOUR,
    CONF_WEEKDAYS_ONLY,
    DEFAULT_END_HOUR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_START_HOUR,
    DEFAULT_WEEKDAYS_ONLY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up My Ride K-12 from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    session = aiohttp_client.async_get_clientsession(hass)
    api = MyRideK12Api(session, username, password)

    async def async_update_data() -> dict[str, Any]:
        """Fetch data from My Ride K-12 API."""
        options = entry.options
        start_hour = options.get(CONF_START_HOUR, DEFAULT_START_HOUR)
        end_hour = options.get(CONF_END_HOUR, DEFAULT_END_HOUR)
        weekdays_only = options.get(CONF_WEEKDAYS_ONLY, DEFAULT_WEEKDAYS_ONLY)

        now = datetime.datetime.now()
        is_active = api.is_in_active_window(
            start_hour=start_hour,
            end_hour=end_hour,
            weekdays_only=weekdays_only,
            now=now,
        )

        try:
            # Fetch student and scan data
            bus_data = await api.fetch_all_bus_data()
            bus_data["is_active_window"] = is_active
            bus_data["last_poll_time"] = now.isoformat()
            return bus_data
        except (MyRideK12ApiError, MyRideK12AuthError) as err:
            _LOGGER.error("Error updating My Ride K-12 data: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    # Use 30 second polling during active window, or 15 mins outside window
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=datetime.timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
