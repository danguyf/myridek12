"""API Client for Tyler Technologies My Ride K-12."""
from __future__ import annotations

import datetime
import json
import logging
import math
from typing import Any

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

from .const import (
    API_BASE_URL,
    COGNITO_CLIENT_ID,
    COGNITO_URL,
    DEFAULT_USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class MyRideK12AuthError(Exception):"""Authentication failed."""


class MyRideK12ApiError(Exception):"""API request failed."""


class MyRideK12Api:
    """Client to interact with the My Ride K-12 API."""

    def __init__(
        self,
        session: Any = None,
        username: str = "",
        password: str = "",
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self.username = username.strip()
        self.password = password.strip()
        self.id_token: str | None = None
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.token_expiry: datetime.datetime | None = None
        self.tenant_id: str | None = None
        self.user_info: dict[str, Any] | None = None

    async def close(self) -> None:
        """Close the dedicated aiohttp session if open."""
        if self._session is not None and hasattr(self._session, "close") and not getattr(self._session, "closed", True):
            await self._session.close()

    def _extract_tenant_from_jwt(self) -> str | None:
        """Extract tenant ID from JWT claims if available."""
        import base64
        for token_str in [self.id_token, self.access_token]:
            if not token_str:
                continue
            try:
                parts = token_str.split(".")
                if len(parts) >= 2:
                    padding = "=" * (4 - len(parts[1]) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8"))
                    groups = payload.get("cognito:groups", [])
                    if groups and len(groups) > 0:
                        return groups[0]
            except Exception as err:
                _LOGGER.debug("Could not parse JWT token for tenant ID: %s", err)
        return None

    async def _make_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
    ) -> tuple[int, dict[str, Any] | list[Any] | str]:
        """Perform HTTP request asynchronously using standard urllib to avoid session header mutations."""
        req_headers = dict(headers) if headers else {}
        req_headers["User-Agent"] = DEFAULT_USER_AGENT

        import urllib.request
        import asyncio

        def _do_http_sync():
            urllib_headers = dict(req_headers)
            urllib_headers["Expect"] = ""  # Prevent urllib 100-continue 417 error on AWS ALB
            kwargs: dict[str, Any] = {"headers": urllib_headers, "method": method}
            if data is not None:
                kwargs["data"] = data
            req = urllib.request.Request(url, **kwargs)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read().decode("utf-8")
                    try:
                        return resp.status, json.loads(raw)
                    except json.JSONDecodeError:
                        return resp.status, raw
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8")
                _LOGGER.debug("HTTPError %s on %s %s: %s", e.code, method, url, raw)
                try:
                    return e.code, json.loads(raw)
                except Exception:
                    return e.code, raw
            except Exception as e:
                _LOGGER.error("Network error on %s %s: %s", method, url, e)
                return 500, str(e)

        return await asyncio.to_thread(_do_http_sync)

    async def authenticate(self) -> bool:
        """Authenticate using AWS Cognito USER_PASSWORD_AUTH."""
        payload = {
            "AuthFlow": "USER_PASSWORD_AUTH",
            "ClientId": COGNITO_CLIENT_ID,
            "AuthParameters": {
                "USERNAME": self.username,
                "PASSWORD": self.password,
            },
        }
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            "User-Agent": DEFAULT_USER_AGENT,
        }

        status, data = await self._make_request(
            COGNITO_URL,
            method="POST",
            headers=headers,
            data=json.dumps(payload).encode("utf-8"),
        )

        if status != 200:
            _LOGGER.error("Cognito authentication failed (%s): %s", status, data)
            raise MyRideK12AuthError(f"Cognito auth failed ({status}): {data}")

        if isinstance(data, dict):
            auth_res = data.get("AuthenticationResult", {})
            self.id_token = auth_res.get("IdToken")
            self.access_token = auth_res.get("AccessToken")
            self.refresh_token = auth_res.get("RefreshToken")
            expires_in = auth_res.get("ExpiresIn", 3600)
            self.token_expiry = datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(seconds=expires_in - 60)

        # Extract tenant ID from JWT tokens
        self.tenant_id = self._extract_tenant_from_jwt()
        _LOGGER.debug("Tenant ID extracted from JWT: %s", self.tenant_id)
        return True

    async def _ensure_authenticated(self) -> None:
        """Ensure token is valid and refresh if needed."""
        now = datetime.datetime.now(datetime.timezone.utc)
        if not self.access_token or not self.token_expiry or now >= self.token_expiry:
            await self.authenticate()

    def _get_api_headers(self) -> dict[str, str]:
        """Get standard HTTP headers for API requests."""
        token = self.access_token or self.id_token
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
        }
        if self.tenant_id:
            headers["x-tenant-id"] = self.tenant_id
        return headers

    async def _fetch_user_info(self) -> dict[str, Any] | None:
        """Fetch user profile to extract tenant/group GUID if available."""
        token = self.access_token or self.id_token
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
        }
        if self.tenant_id:
            headers["x-tenant-id"] = self.tenant_id

        url = f"{API_BASE_URL}/api/user"

        try:
            status, data = await self._make_request(url, method="GET", headers=headers)
            if status == 200 and isinstance(data, dict):
                self.user_info = data
                groups = data.get("groups", [])
                if groups and not self.tenant_id:
                    self.tenant_id = groups[0].get("groupGuid")
                    _LOGGER.debug("Extracted tenant ID from /api/user: %s", self.tenant_id)
                return data
            _LOGGER.debug("Non-critical: /api/user returned HTTP %s: %s", status, data)
        except Exception as err:
            _LOGGER.debug("Non-critical: Error fetching /api/user: %s", err)
        return None

    async def get_students(self) -> list[dict[str, Any]]:
        """Fetch student details and assigned bus runs."""
        await self._ensure_authenticated()
        url = f"{API_BASE_URL}/api/student"

        status, data = await self._make_request(
            url, method="GET", headers=self._get_api_headers()
        )
        if status == 401:
            _LOGGER.info("Received 401 fetching students, re-authenticating and retrying...")
            await self.authenticate()
            status, data = await self._make_request(
                url, method="GET", headers=self._get_api_headers()
            )

        if status == 200 and isinstance(data, list):
            return data
        _LOGGER.error("Failed to fetch students (HTTP %s): %s", status, data)
        raise MyRideK12ApiError(f"Failed to fetch students: {status}")

    async def get_student_scans(self) -> list[dict[str, Any]]:
        """Fetch student bus stop scans and stop coordinates."""
        await self._ensure_authenticated()
        url = f"{API_BASE_URL}/api/scan"

        status, data = await self._make_request(
            url, method="GET", headers=self._get_api_headers()
        )
        if status == 401:
            _LOGGER.info("Received 401 fetching scans, re-authenticating and retrying...")
            await self.authenticate()
            status, data = await self._make_request(
                url, method="GET", headers=self._get_api_headers()
            )

        if status == 200 and isinstance(data, list):
            return data
        _LOGGER.error("Failed to fetch student scans (HTTP %s): %s", status, data)
        raise MyRideK12ApiError(f"Failed to fetch student scans: {status}")

    async def fetch_all_bus_data(self) -> dict[str, Any]:
        """Fetch consolidated student, route, and stop data per student."""
        await self._ensure_authenticated()

        students = await self.get_students()
        scans = await self.get_student_scans()

        # Index latest scan by studentId
        scans_by_student: dict[int, dict[str, Any]] = {}
        for scan in scans:
            st_id = scan.get("studentId")
            if st_id and st_id not in scans_by_student:
                scans_by_student[st_id] = scan

        students_map: dict[int, dict[str, Any]] = {}
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

            scan = scans_by_student.get(st_id, {})

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
                "stop_location": scan.get("scanLocation"),
                "stop_latitude": scan.get("stopLatitude"),
                "stop_longitude": scan.get("stopLongitude"),
                "last_scan_time": scan.get("scanDateTime"),
                "last_scan_state": scan.get("scanState"),
            }

        return {
            "students": students,
            "scans": scans,
            "students_map": students_map,
        }

    @staticmethod
    def calculate_distance(
        lat1: float, lon1: float, lat2: float, lon2: float, unit: str = "mi"
    ) -> float:
        """Calculate Haversine distance between two GPS coordinates."""
        r_earth = 3958.8 if unit == "mi" else 6371.0  # Radius of earth in miles or kilometers

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(r_earth * c, 2)

    @staticmethod
    def is_in_active_window(
        start_hour: int = 6,
        end_hour: int = 8,
        weekdays_only: bool = True,
        now: datetime.datetime | None = None,
    ) -> bool:
        """Check if current local time is within the active monitoring window."""
        if now is None:
            now = datetime.datetime.now()

        if weekdays_only and now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        return start_hour <= now.hour < end_hour
