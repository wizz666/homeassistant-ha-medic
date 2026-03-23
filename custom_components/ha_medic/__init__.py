"""HA Medic — AI-powered log diagnostics for Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, CONF_SCAN_INTERVAL
from .coordinator import HaMedicCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    coordinator = HaMedicCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _register_services(hass, coordinator)
    _schedule_analysis(hass, entry, coordinator)

    # Listen for mobile app notification actions (approve/decline buttons)
    async def _handle_mobile_action(event) -> None:
        action = event.data.get("action", "")
        if action.startswith("HAMEDIC_APPROVE_"):
            fix_id = action[len("HAMEDIC_APPROVE_"):]
            await coordinator.async_approve(fix_id)
        elif action.startswith("HAMEDIC_DECLINE_"):
            fix_id = action[len("HAMEDIC_DECLINE_"):]
            await coordinator.async_decline(fix_id)

    entry.async_on_unload(
        hass.bus.async_listen("mobile_app_notification_action", _handle_mobile_action)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _unregister_services(hass)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant, coordinator: HaMedicCoordinator) -> None:
    async def handle_analyze(call: ServiceCall) -> None:
        await coordinator.async_analyze()

    async def handle_approve(call: ServiceCall) -> None:
        fix_id = call.data.get("fix_id")
        await coordinator.async_approve(fix_id)

    async def handle_decline(call: ServiceCall) -> None:
        fix_id = call.data.get("fix_id")
        await coordinator.async_decline(fix_id)

    async def handle_dismiss_all(call: ServiceCall) -> None:
        await coordinator.async_dismiss_all()

    hass.services.async_register(DOMAIN, "analyze", handle_analyze)
    hass.services.async_register(
        DOMAIN,
        "approve",
        handle_approve,
        schema=vol.Schema({vol.Optional("fix_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        "decline",
        handle_decline,
        schema=vol.Schema({vol.Optional("fix_id"): cv.string}),
    )
    hass.services.async_register(DOMAIN, "dismiss_all", handle_dismiss_all)


def _unregister_services(hass: HomeAssistant) -> None:
    for service in ("analyze", "approve", "decline", "dismiss_all"):
        hass.services.async_remove(DOMAIN, service)


def _schedule_analysis(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: HaMedicCoordinator
) -> None:
    interval_hours = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, 0)
    )
    if not interval_hours:
        return

    async def _scheduled(_now) -> None:
        _LOGGER.debug("HA Medic: scheduled analysis triggered")
        await coordinator.async_analyze()

    cancel = async_track_time_interval(
        hass, _scheduled, timedelta(hours=interval_hours)
    )
    entry.async_on_unload(cancel)
