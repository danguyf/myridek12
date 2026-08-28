#!/usr/bin/env python3
"""End-to-End simulation test that mocks the exact Home Assistant integration lifecycle."""
import asyncio
import datetime
import importlib.util
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_ha_e2e")

USERNAME = os.getenv("MYRIDEK12_USERNAME") or (sys.argv[1] if len(sys.argv) > 1 else "")
PASSWORD = os.getenv("MYRIDEK12_PASSWORD") or (sys.argv[2] if len(sys.argv) > 2 else "")

if not USERNAME or not PASSWORD:
    logger.error("Usage: python3 test_e2e_lifecycle.py <email> <password>")
    sys.exit(1)

# Import integration modules
repo_root = Path(__file__).parent
custom_comp = repo_root / "custom_components" / "myridek12"

# 1. const.py
spec_c = importlib.util.spec_from_file_location("custom_components.myridek12.const", custom_comp / "const.py")
const_mod = importlib.util.module_from_spec(spec_c)
sys.modules["custom_components.myridek12.const"] = const_mod
spec_c.loader.exec_module(const_mod)

# Mock homeassistant base modules if not installed
import types

ha_mod = types.ModuleType("homeassistant")
sys.modules["homeassistant"] = ha_mod

ha_sensor_mod = types.ModuleType("homeassistant.components.sensor")
class MockSensorStateClass:
    MEASUREMENT = "measurement"
class MockSensorEntity:
    pass
ha_sensor_mod.SensorEntity = MockSensorEntity
ha_sensor_mod.SensorStateClass = MockSensorStateClass
sys.modules["homeassistant.components"] = types.ModuleType("homeassistant.components")
sys.modules["homeassistant.components.sensor"] = ha_sensor_mod

ha_coord_mod = types.ModuleType("homeassistant.helpers.update_coordinator")
class MockCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator
ha_coord_mod.CoordinatorEntity = MockCoordinatorEntity
ha_coord_mod.DataUpdateCoordinator = object
sys.modules["homeassistant.helpers"] = types.ModuleType("homeassistant.helpers")
sys.modules["homeassistant.helpers.update_coordinator"] = ha_coord_mod
ha_cfg_mod = types.ModuleType("homeassistant.config_entries")
ha_cfg_mod.ConfigEntry = object
sys.modules["homeassistant.config_entries"] = ha_cfg_mod

ha_ep_mod = types.ModuleType("homeassistant.helpers.entity_platform")
ha_ep_mod.AddEntitiesCallback = object
sys.modules["homeassistant.helpers.entity_platform"] = ha_ep_mod
ha_core_mod = types.ModuleType("homeassistant.core")
ha_core_mod.HomeAssistant = object
sys.modules["homeassistant.core"] = ha_core_mod

# 2. api.py
spec_a = importlib.util.spec_from_file_location("custom_components.myridek12.api", custom_comp / "api.py")
api_mod = importlib.util.module_from_spec(spec_a)
api_mod.__package__ = "custom_components.myridek12"
sys.modules["custom_components.myridek12.api"] = api_mod
spec_a.loader.exec_module(api_mod)
MyRideK12Api = api_mod.MyRideK12Api


# =========================================================================
# Mock Home Assistant Core Environment
# =========================================================================

class MockConfigEntry:
    """Mocks Home Assistant's ConfigEntry."""
    def __init__(self, entry_id: str, data: dict, options: dict):
        self.entry_id = entry_id
        self.data = data
        self.options = options


class MockDataUpdateCoordinator:
    """Mocks Home Assistant's DataUpdateCoordinator."""
    def __init__(self, name: str, update_method):
        self.name = name
        self.update_method = update_method
        self.data = None

    async def async_config_entry_first_refresh(self):
        logger.info("[Coordinator] Executing first refresh...")
        self.data = await self.update_method()
        logger.info("[Coordinator] First refresh completed successfully. Got %s student(s)", len(self.data.get("students", [])))

    async def async_refresh(self):
        logger.info("[Coordinator] Executing scheduled refresh...")
        self.data = await self.update_method()


# =========================================================================
# End-to-End Lifecycle Execution
# =========================================================================

async def simulate_home_assistant_lifecycle():
    logger.info("=====================================================================")
    logger.info("PHASE 1: Simulating Config Flow (UI Authentication Step)")
    logger.info("=====================================================================")
    # Step 1: Config Flow runs authenticate() on a fresh API instance
    config_api = MyRideK12Api(None, USERNAME, PASSWORD)
    auth_result = await config_api.authenticate()
    assert auth_result is True, "Config flow authenticate failed"
    assert config_api.tenant_id is not None, "Tenant ID not found in token"
    logger.info("✓ Config Flow Auth OK! Tenant ID: %s", config_api.tenant_id)
    await config_api.close()

    # Step 2: Home Assistant creates ConfigEntry
    config_entry = MockConfigEntry(
        entry_id="mock_entry_12345",
        data={"username": USERNAME, "password": PASSWORD},
        options={"start_hour": 6, "end_hour": 8, "weekdays_only": True, "distance_unit": "mi"},
    )
    logger.info("✓ Created ConfigEntry: %s", config_entry.entry_id)

    logger.info("=====================================================================")
    logger.info("PHASE 2: Simulating async_setup_entry (__init__.py coordinator setup)")
    logger.info("=====================================================================")
    # Step 3: Integration instantiation (same as __init__.py async_setup_entry)
    api = MyRideK12Api(None, config_entry.data["username"], config_entry.data["password"])

    async def async_update_data() -> dict[str, Any]:
        options = config_entry.options
        now = datetime.datetime.now()
        is_active = api.is_in_active_window(
            start_hour=options.get("start_hour", 6),
            end_hour=options.get("end_hour", 8),
            weekdays_only=options.get("weekdays_only", True),
            now=now,
        )
        bus_data = await api.fetch_all_bus_data()
        bus_data["is_active_window"] = is_active
        bus_data["last_poll_time"] = now.isoformat()
        return bus_data

    coordinator = MockDataUpdateCoordinator("myridek12", async_update_data)
    await coordinator.async_config_entry_first_refresh()

    logger.info("=====================================================================")
    logger.info("PHASE 3: Simulating Sensor Platform Entities Creation (sensor.py)")
    logger.info("=====================================================================")
    # Import sensor.py
    spec_s = importlib.util.spec_from_file_location("custom_components.myridek12.sensor", custom_comp / "sensor.py")
    sensor_mod = importlib.util.module_from_spec(spec_s)
    sensor_mod.__package__ = "custom_components.myridek12"
    sys.modules["custom_components.myridek12.sensor"] = sensor_mod
    spec_s.loader.exec_module(sensor_mod)
    MyRideK12SchoolBusDistanceSensor = sensor_mod.MyRideK12SchoolBusDistanceSensor

    students = coordinator.data.get("students", [])
    logger.info("Found %d students in coordinator data", len(students))
    for st in students:
        sensor_entity = MyRideK12SchoolBusDistanceSensor(coordinator, config_entry, st)
        dist_val = sensor_entity.native_value
        attrs = sensor_entity.extra_state_attributes
        logger.info("✓ Sensor Entity '%s' (unique_id='%s'):", sensor_entity._attr_name, sensor_entity._attr_unique_id)
        logger.info("   -> State (native_value): %s %s", dist_val, sensor_entity.native_unit_of_measurement)
        logger.info("   -> Attributes: Stop='%s' (lat=%s, lon=%s)", attrs.get("stop_location"), attrs.get("stop_latitude"), attrs.get("stop_longitude"))
        logger.info("   -> Attributes: Bus='%s', Vehicle='%s', Driver='%s'", attrs.get("bus_number"), attrs.get("active_vehicle"), attrs.get("driver_name"))
        assert dist_val is not None and isinstance(dist_val, (float, int)), "Sensor native_value must be a numeric float"

    logger.info("=====================================================================")
    logger.info("PHASE 4: Simulating 2nd Periodic Coordinator Poll (After interval)")
    logger.info("=====================================================================")
    await coordinator.async_refresh()
    logger.info("✓ Second coordinator poll completed successfully!")

    logger.info("=====================================================================")
    logger.info("PHASE 5: Simulating Integration Unload (async_unload_entry)")
    logger.info("=====================================================================")
    await api.close()
    logger.info("✓ Cleanup & session close completed!")

    logger.info("=====================================================================")
    logger.info("ALL END-TO-END HOME ASSISTANT LIFECYCLE TESTS COMPLETED SUCCESSFULLY!")
    logger.info("=====================================================================")


if __name__ == "__main__":
    asyncio.run(simulate_home_assistant_lifecycle())
