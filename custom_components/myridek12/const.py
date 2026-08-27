"""Constants for the My Ride K-12 integration."""
from typing import Final

DOMAIN: Final = "myridek12"
NAME: Final = "My Ride K-12"
VERSION: Final = "1.0.0"

# AWS Cognito Configuration
COGNITO_REGION: Final = "us-east-1"
COGNITO_USER_POOL_ID: Final = "us-east-1_sfRczsC0e"
COGNITO_CLIENT_ID: Final = "3c5382gsq7g13djnejo98p2d98"
COGNITO_URL: Final = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"

# API Configuration
API_BASE_URL: Final = "https://myridek12.tylerapi.com"
DEFAULT_USER_AGENT: Final = "myridek12"

# Configuration options
CONF_START_HOUR: Final = "start_hour"
CONF_END_HOUR: Final = "end_hour"
CONF_WEEKDAYS_ONLY: Final = "weekdays_only"
CONF_DISTANCE_UNIT: Final = "distance_unit"
CONF_REF_LATITUDE: Final = "ref_latitude"
CONF_REF_LONGITUDE: Final = "ref_longitude"

# Default values
DEFAULT_START_HOUR: Final = 6
DEFAULT_END_HOUR: Final = 8
DEFAULT_WEEKDAYS_ONLY: Final = True
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
DEFAULT_DISTANCE_UNIT: Final = "mi"
