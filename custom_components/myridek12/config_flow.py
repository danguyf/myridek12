"""Config flow for My Ride K-12 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.config_validation as cv

from .api import MyRideK12Api, MyRideK12AuthError, MyRideK12ApiError
from .const import (
    CONF_DISTANCE_UNIT,
    CONF_END_HOUR,
    CONF_START_HOUR,
    CONF_WEEKDAYS_ONLY,
    DEFAULT_DISTANCE_UNIT,
    DEFAULT_END_HOUR,
    DEFAULT_START_HOUR,
    DEFAULT_WEEKDAYS_ONLY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class MyRideK12ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for My Ride K-12."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD].strip()

            # Unique ID based on email address
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            session = aiohttp_client.async_get_clientsession(self.hass)
            api = MyRideK12Api(session, username, password)

            try:
                await api.authenticate()
            except MyRideK12AuthError:
                errors["base"] = "invalid_auth"
            except MyRideK12ApiError:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"My Ride K-12 ({username})",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                    options={
                        CONF_START_HOUR: DEFAULT_START_HOUR,
                        CONF_END_HOUR: DEFAULT_END_HOUR,
                        CONF_WEEKDAYS_ONLY: DEFAULT_WEEKDAYS_ONLY,
                        CONF_DISTANCE_UNIT: DEFAULT_DISTANCE_UNIT,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return MyRideK12OptionsFlowHandler(config_entry)


class MyRideK12OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle My Ride K-12 options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_START_HOUR,
                    default=options.get(CONF_START_HOUR, DEFAULT_START_HOUR),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                vol.Optional(
                    CONF_END_HOUR,
                    default=options.get(CONF_END_HOUR, DEFAULT_END_HOUR),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                vol.Optional(
                    CONF_WEEKDAYS_ONLY,
                    default=options.get(CONF_WEEKDAYS_ONLY, DEFAULT_WEEKDAYS_ONLY),
                ): cv.boolean,
                vol.Optional(
                    CONF_DISTANCE_UNIT,
                    default=options.get(CONF_DISTANCE_UNIT, DEFAULT_DISTANCE_UNIT),
                ): vol.In(["mi", "km"]),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
