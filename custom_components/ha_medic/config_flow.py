"""Config flow for HA Medic."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_AI_PROVIDER,
    CONF_AI_KEY,
    CONF_AI_BASE_URL,
    CONF_AI_MODEL,
    CONF_NOTIFY_SERVICE,
    CONF_INCLUDE_ADDON_LOGS,
    CONF_SCAN_INTERVAL,
    DEFAULT_PROVIDER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_INCLUDE_ADDON_LOGS,
    PROVIDERS,
    SCAN_INTERVALS,
)


def _provider_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_AI_PROVIDER, default=defaults.get(CONF_AI_PROVIDER, DEFAULT_PROVIDER)):
            vol.In(PROVIDERS),
        vol.Optional(CONF_AI_KEY, default=defaults.get(CONF_AI_KEY, "")):
            str,
        vol.Optional(CONF_AI_BASE_URL, default=defaults.get(CONF_AI_BASE_URL, "")):
            str,
        vol.Optional(CONF_AI_MODEL, default=defaults.get(CONF_AI_MODEL, "")):
            str,
    })


def _options_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_AI_PROVIDER, default=defaults.get(CONF_AI_PROVIDER, DEFAULT_PROVIDER)):
            vol.In(PROVIDERS),
        vol.Optional(CONF_AI_KEY, default=defaults.get(CONF_AI_KEY, "")):
            str,
        vol.Optional(CONF_AI_BASE_URL, default=defaults.get(CONF_AI_BASE_URL, "")):
            str,
        vol.Optional(CONF_AI_MODEL, default=defaults.get(CONF_AI_MODEL, "")):
            str,
        vol.Optional(CONF_NOTIFY_SERVICE, default=defaults.get(CONF_NOTIFY_SERVICE, "")):
            str,
        vol.Optional(
            CONF_INCLUDE_ADDON_LOGS,
            default=defaults.get(CONF_INCLUDE_ADDON_LOGS, DEFAULT_INCLUDE_ADDON_LOGS),
        ): bool,
        vol.Optional(
            CONF_SCAN_INTERVAL,
            default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ): vol.In(SCAN_INTERVALS),
    })


class HaMedicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="HA Medic", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_provider_schema({}),
            errors=errors,
            description_placeholders={
                "groq_url": "console.groq.com",
                "openrouter_url": "openrouter.ai/keys",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HaMedicOptionsFlow(config_entry)


class HaMedicOptionsFlow(OptionsFlow):
    """Handle options (reconfigure)."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = {**self._entry.data, **self._entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(defaults),
        )
