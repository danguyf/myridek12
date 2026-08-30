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

from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

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


def get_next_window_start(
    start_hour: int,
    end_hour: int,
    weekdays_only: bool,
    now: datetime.datetime,
) -> datetime.datetime:
    """Calculate the exact datetime for the start of the next active monitoring window."""
    candidate = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    # If candidate start is already in the past for today, begin searching from tomorrow
    if now >= candidate:
        candidate += datetime.timedelta(days=1)

    # If weekdays only, advance candidate until it lands on a Monday-Friday
    if weekdays_only:
        while candidate.weekday() >= 5:  # 5=Saturday, 6=Sunday
            candidate += datetime.timedelta(days=1)

    return candidate


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up My Ride K-12 from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    api = MyRideK12Api(None, username, password)
    cancel_wakeup_listener: Any = None

    def _schedule_next_wakeup(now: datetime.datetime) -> None:
        """Schedule a wake-up callback at the start of the next active window."""
        nonlocal cancel_wakeup_listener
        if cancel_wakeup_listener is not None:
            cancel_wakeup_listener()
            cancel_wakeup_listener = None

        options = entry.options
        start_hour = options.get(CONF_START_HOUR, DEFAULT_START_HOUR)
        end_hour = options.get(CONF_END_HOUR, DEFAULT_END_HOUR)
        weekdays_only = options.get(CONF_WEEKDAYS_ONLY, DEFAULT_WEEKDAYS_ONLY)

        next_start = get_next_window_start(start_hour, end_hour, weekdays_only, now)
        _LOGGER.info("Scheduling next active window wake-up for %s", next_start.isoformat())

        async def _wakeup_callback(_datetime_point: datetime.datetime) -> None:
            _LOGGER.info("Active window reached (%s). Resuming 5s active polling.", _datetime_point.isoformat())
            coordinator.update_interval = datetime.timedelta(seconds=DEFAULT_SCAN_INTERVAL)
            await coordinator.async_request_refresh()

        cancel_wakeup_listener = async_track_point_in_time(hass, _wakeup_callback, next_start)

    async def async_update_data() -> dict[str, Any]:
        """Fetch data from My Ride K-12 API during active window."""
        options = entry.options
        start_hour = options.get(CONF_START_HOUR, DEFAULT_START_HOUR)
        end_hour = options.get(CONF_END_HOUR, DEFAULT_END_HOUR)
        weekdays_only = options.get(CONF_WEEKDAYS_ONLY, DEFAULT_WEEKDAYS_ONLY)

        now = dt_util.now()
        is_active = api.is_in_active_window(
            start_hour=start_hour,
            end_hour=end_hour,
            weekdays_only=weekdays_only,
            now=now,
        )

        # When outside active window, completely disable coordinator interval timer and schedule wake-up
        if not is_active:
            api.stop_live_stream()
            if coordinator.update_interval is not None:
                coordinator.update_interval = None
                _LOGGER.info(
                    "Active window ended (%02d:00 - %02d:00). Disabled polling interval (set to None).",
                    start_hour,
                    end_hour,
                )
            _schedule_next_wakeup(now)

            cached_data = coordinator.data or {}
            students = cached_data.get("students", [])
            students_map = cached_data.get("students_map", {})
            scans = cached_data.get("scans", [])

            # On initial startup outside active window, fetch student roster once so entities are properly named
            if not students:
                try:
                    _LOGGER.info("Initial startup outside active window: fetching student roster.")
                    students = await api.get_students()
                    for student in students:
                        st_id = student.get("studentId")
                        if not st_id:
                            continue
                        run_info = student.get("runInfo", [])
                        bus_number = None
                        active_vehicle = None
                        route_name = None
                        driver_name = None
                        if run_info:
                            run = run_info[0]
                            bus_number = run.get("busNumber")
                            active_vehicle = run.get("activeVehicle") or run.get("rolloutBusNumber")
                            route_name = run.get("visibleName") or run.get("runName")
                            driver_name = run.get("driverName")

                        students_map[st_id] = {
                            "student": student,
                            "student_id": st_id,
                            "first_name": student.get("firstName", ""),
                            "last_name": student.get("lastName", ""),
                            "school_name": student.get("locationName"),
                            "bus_number": bus_number,
                            "active_vehicle": active_vehicle,
                            "route_name": route_name,
                            "driver_name": driver_name,
                            "stop_location": None,
                            "stop_latitude": None,
                            "stop_longitude": None,
                            "bus_latitude": None,
                            "bus_longitude": None,
                            "last_scan_time": None,
                            "last_scan_state": None,
                        }
                except Exception as err:
                    _LOGGER.warning("Could not fetch student roster on initial startup: %s", err)

            return {
                "students": students,
                "scans": scans,
                "students_map": students_map,
                "is_active_window": False,
                "last_poll_time": now.isoformat(),
            }

        # Inside active window: ensure 5s interval is active
        target_interval = datetime.timedelta(seconds=DEFAULT_SCAN_INTERVAL)
        if coordinator.update_interval != target_interval:
            coordinator.update_interval = target_interval

        try:
            # Fetch student and scan data only during active window
            bus_data = await api.fetch_all_bus_data()
            bus_data["is_active_window"] = is_active
            bus_data["last_poll_time"] = now.isoformat()
            return bus_data
        except (MyRideK12ApiError, MyRideK12AuthError) as err:
            _LOGGER.error("Error updating My Ride K-12 data: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    # Initialize coordinator
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
        "cancel_wakeup": lambda: cancel_wakeup_listener() if cancel_wakeup_listener else None,
    }

    # Register listener for option updates (e.g. changing active hours)
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update by restoring active polling and refreshing coordinator."""
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        coordinator.update_interval = datetime.timedelta(seconds=DEFAULT_SCAN_INTERVAL)
        await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        data = hass.data[DOMAIN].pop(entry.entry_id, {})
        if "api" in data:
            await data["api"].close()

    return unload_ok
