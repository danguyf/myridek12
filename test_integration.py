#!/usr/bin/env python3
"""Verification test script for My Ride K-12 integration logic."""
import asyncio
import datetime
import importlib.util
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_integration")

# Import const.py and api.py with proper package binding
const_path = Path(__file__).parent / "custom_components" / "myridek12" / "const.py"
spec_c = importlib.util.spec_from_file_location("custom_components.myridek12.const", const_path)
const_mod = importlib.util.module_from_spec(spec_c)
sys.modules["custom_components.myridek12.const"] = const_mod
spec_c.loader.exec_module(const_mod)

api_path = Path(__file__).parent / "custom_components" / "myridek12" / "api.py"
spec_a = importlib.util.spec_from_file_location("custom_components.myridek12.api", api_path)
myridek12_api = importlib.util.module_from_spec(spec_a)
myridek12_api.__package__ = "custom_components.myridek12"
sys.modules["custom_components.myridek12.api"] = myridek12_api
spec_a.loader.exec_module(myridek12_api)
MyRideK12Api = myridek12_api.MyRideK12Api

USERNAME = os.getenv("MYRIDEK12_USERNAME") or (sys.argv[1] if len(sys.argv) > 1 else "")
PASSWORD = os.getenv("MYRIDEK12_PASSWORD") or (sys.argv[2] if len(sys.argv) > 2 else "")

if not USERNAME or not PASSWORD:
    logger.error("Credentials not provided!")
    logger.error("Usage: python3 test_integration.py <email> <password>")
    logger.error("   or: MYRIDEK12_USERNAME=email MYRIDEK12_PASSWORD=pass python3 test_integration.py")
    sys.exit(1)


class MockAiohttpResponse:
    def __init__(self, status: int, raw_text: str):
        self.status = status
        self._raw_text = raw_text

    async def json(self):
        import json
        return json.loads(self._raw_text)

    async def text(self):
        return self._raw_text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockAiohttpSession:
    """Mock aiohttp.ClientSession that uses urllib to simulate aiohttp execution."""

    def request(self, method, url, headers=None, data=None, **kwargs):
        import urllib.request
        req_headers = dict(headers) if headers else {}
        req_kwargs = {"headers": req_headers, "method": method}
        if data is not None:
            req_kwargs["data"] = data

        req = urllib.request.Request(url, **req_kwargs)
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8")
                return MockAiohttpResponse(status, raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8")
            return MockAiohttpResponse(e.code, raw)


async def run_test_suite(session_obj, mode_name: str):
    logger.info("============================================================")
    logger.info("Running Test Suite (%s)...", mode_name)
    logger.info("============================================================")
    api = MyRideK12Api(session_obj, USERNAME, PASSWORD)

    logger.info("Testing AWS Cognito Authentication...")
    auth_success = await api.authenticate()
    assert auth_success is True, "Authentication failed"
    assert api.tenant_id is not None, "Tenant ID extraction failed"
    logger.info("✓ Authentication & Tenant ID Extracted: %s", api.tenant_id)

    logger.info("Testing get_students()...")
    students = await api.get_students()
    assert len(students) > 0, "No students returned"
    student = students[0]
    logger.info(
        "✓ Student Found: %s %s (ID: %s, School: %s)",
        student.get("firstName"),
        student.get("lastName"),
        student.get("studentId"),
        student.get("locationName"),
    )

    logger.info("Testing get_student_scans()...")
    scans = await api.get_student_scans()
    assert len(scans) > 0, "No scans returned"
    scan = scans[0]
    logger.info(
        "✓ Stop Location Found: %s (Lat: %s, Lon: %s)",
        scan.get("scanLocation"),
        scan.get("stopLatitude"),
        scan.get("stopLongitude"),
    )

    logger.info("Testing fetch_all_bus_data()...")
    bus_data = await api.fetch_all_bus_data()
    students_map = bus_data.get("students_map", {})
    assert len(students_map) > 0, "No students mapped in students_map"
    for st_id, st_info in students_map.items():
        logger.info(
            "✓ Per-Child Sensor Entity Ready -> Student ID: %s (%s %s), Bus: %s, Vehicle: %s, Route: %s, Driver: %s",
            st_id,
            st_info.get("first_name"),
            st_info.get("last_name"),
            st_info.get("bus_number"),
            st_info.get("active_vehicle"),
            st_info.get("route_name"),
            st_info.get("driver_name"),
        )

    logger.info("Testing distance calculation (Haversine)...")
    dist_mi = api.calculate_distance(38.28657, -77.50289, 38.30000, -77.52000, "mi")
    logger.info("✓ Calculated Distance: %s miles", dist_mi)

    logger.info("Testing active window evaluation (6:00 - 8:00 AM)...")
    morning_time = datetime.datetime(2026, 8, 27, 7, 15, 0)
    night_time = datetime.datetime(2026, 8, 27, 21, 15, 0)
    assert api.is_in_active_window(6, 8, True, morning_time) is True
    assert api.is_in_active_window(6, 8, True, night_time) is False
    logger.info("✓ Active window filter logic verified.")


async def main():
    # Test 1: Standard urllib mode (session=None)
    await run_test_suite(None, "Standalone urllib mode")

    # Test 2: Simulated aiohttp Session mode (session=MockAiohttpSession())
    await run_test_suite(MockAiohttpSession(), "Simulated aiohttp Session mode")

    logger.info("============================================================")
    logger.info("ALL VERIFICATION TESTS PASSED (BOTH SESSION MODES)!")
    logger.info("============================================================")


if __name__ == "__main__":
    asyncio.run(main())
