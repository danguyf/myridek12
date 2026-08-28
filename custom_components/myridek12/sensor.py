"""Sensor platform for My Ride K-12 integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import MyRideK12Api
from .const import (
    CONF_DISTANCE_UNIT,
    CONF_END_HOUR,
    CONF_START_HOUR,
    DEFAULT_DISTANCE_UNIT,
    DEFAULT_END_HOUR,
    DEFAULT_START_HOUR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up My Ride K-12 sensor entities (one per child)."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DataUpdateCoordinator = data["coordinator"]

    students = coordinator.data.get("students", []) if coordinator.data else []

    entities: list[MyRideK12SchoolBusDistanceSensor] = []
    for student in students:
        entities.append(
            MyRideK12SchoolBusDistanceSensor(coordinator, entry, student)
        )

    if not entities:
        # Fallback if no students returned yet
        entities.append(MyRideK12SchoolBusDistanceSensor(coordinator, entry, {}))

    async_add_entities(entities)


class MyRideK12SchoolBusDistanceSensor(CoordinatorEntity, SensorEntity):
    """Representation of the School Bus Distance Sensor for a specific student."""

    _attr_icon = "mdi:bus-school"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        student: dict[str, Any],
    ) -> None:
        """Initialize the sensor for a specific child."""
        super().__init__(coordinator)
        self.entry = entry
        self.student_id = student.get("studentId", "default")
        
        first_name = student.get("firstName", "")
        last_name = student.get("lastName", "")
        full_name_clean = f"{first_name}{last_name}".strip()

        self.student_name = full_name_clean or f"Student_{self.student_id}"

        # Unique ID uses student ID for stability
        self._attr_unique_id = f"myridek12_bus_distance_{self.student_id}"

        # Entity Name format yields entity_id sensor.school_bus_distance_<FirstName><LastName>
        if full_name_clean:
            self._attr_name = f"School Bus Distance {full_name_clean}"
        else:
            self._attr_name = "School Bus Distance"

    def _get_student_data(self) -> dict[str, Any]:
        """Get student-specific data from coordinator data."""
        if not self.coordinator.data:
            return {}
        students_map = self.coordinator.data.get("students_map", {})
        return students_map.get(self.student_id, {})

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return self.entry.options.get(CONF_DISTANCE_UNIT, DEFAULT_DISTANCE_UNIT)

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor as a numeric distance value."""
        if not self.coordinator.data:
            return -1.0

        is_active = self.coordinator.data.get("is_active_window", False)
        if not is_active:
            return -1.0

        st_data = self._get_student_data()

        # Extract stop coordinates for this child
        stop_lat = st_data.get("stop_latitude")
        stop_lon = st_data.get("stop_longitude")

        # If live bus coordinates exist in coordinator data, calculate distance to stop
        bus_lat = st_data.get("bus_latitude")
        bus_lon = st_data.get("bus_longitude")

        unit = self.native_unit_of_measurement

        if bus_lat is not None and bus_lon is not None and stop_lat is not None and stop_lon is not None:
            return MyRideK12Api.calculate_distance(
                bus_lat, bus_lon, stop_lat, stop_lon, unit=unit
            )

        # When vehicle is at the stop or scan location is confirmed, distance to stop is 0.0
        if stop_lat is not None and stop_lon is not None:
            return 0.0

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        if not self.coordinator.data:
            return {}

        st_data = self._get_student_data()
        start_h = self.entry.options.get(CONF_START_HOUR, DEFAULT_START_HOUR)
        end_h = self.entry.options.get(CONF_END_HOUR, DEFAULT_END_HOUR)

        first_name = st_data.get("first_name", "")
        last_name = st_data.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip()

        is_active = self.coordinator.data.get("is_active_window", False)
        status = "Active" if is_active else "Inactive"

        return {
            "distance": self.native_value,
            "status": status,
            "student_name": full_name,
            "student_id": self.student_id,
            "school_name": st_data.get("school_name"),
            "bus_number": st_data.get("bus_number"),
            "active_vehicle": st_data.get("active_vehicle"),
            "route_name": st_data.get("route_name"),
            "driver_name": st_data.get("driver_name"),
            "stop_location": st_data.get("stop_location"),
            "stop_latitude": st_data.get("stop_latitude"),
            "stop_longitude": st_data.get("stop_longitude"),
            "last_scan_time": st_data.get("last_scan_time"),
            "last_scan_state": st_data.get("last_scan_state"),
            "active_window": is_active,
            "active_window_hours": f"{start_h:02d}:00 - {end_h:02d}:00",
            "last_poll_time": self.coordinator.data.get("last_poll_time"),
        }
