"""HA Medic sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HaMedicCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HaMedicCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_load_queue()
    async_add_entities([
        HaMedicStatusSensor(coordinator, entry),
        HaMedicFindingsSensor(coordinator, entry),
        HaMedicPendingSensor(coordinator, entry),
    ])


class _HaMedicBaseSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: HaMedicCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry

    async def async_added_to_hass(self) -> None:
        self._coordinator.async_add_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "HA Medic",
            "manufacturer": "HA Medic",
            "model": "AI Log Diagnostics",
            "entry_type": "service",
        }


class HaMedicStatusSensor(_HaMedicBaseSensor):
    _attr_icon = "mdi:stethoscope"

    def __init__(self, coordinator: HaMedicCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_name = "Status"

    @property
    def native_value(self) -> str:
        return self._coordinator.status

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "summary": self._coordinator.summary,
            "last_run": self._coordinator.last_run,
        }


class HaMedicFindingsSensor(_HaMedicBaseSensor):
    _attr_icon = "mdi:clipboard-pulse"
    _attr_native_unit_of_measurement = "findings"

    def __init__(self, coordinator: HaMedicCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_findings"
        self._attr_name = "Findings"

    @property
    def native_value(self) -> int:
        return len(self._coordinator.findings)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "findings": self._coordinator.findings,
            "summary": self._coordinator.summary,
            "last_run": self._coordinator.last_run,
        }


class HaMedicPendingSensor(_HaMedicBaseSensor):
    _attr_icon = "mdi:checkbox-marked-circle-auto-outline"
    _attr_native_unit_of_measurement = "pending"

    def __init__(self, coordinator: HaMedicCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_pending"
        self._attr_name = "Pending"

    @property
    def native_value(self) -> int:
        return len(self._coordinator.pending)

    @property
    def extra_state_attributes(self) -> dict:
        pending = self._coordinator.pending
        first = pending[0] if pending else {}
        return {
            "pending": pending,
            "first_id": first.get("id", ""),
            "first_title": first.get("title", ""),
            "first_suggestion": first.get("suggestion", ""),
            "first_fix_type": first.get("fix_type", ""),
        }
