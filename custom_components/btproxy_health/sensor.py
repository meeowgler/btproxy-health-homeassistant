"""Per-proxy health sensors, attached to the proxy's existing device."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ProxyHealthConfigEntry
from .coordinator import ProxyHealthCoordinator, ProxyInfo, ProxySnapshot


@dataclass(frozen=True, kw_only=True)
class ProxySensorDescription(SensorEntityDescription):
    """Describes a proxy health sensor."""

    value_fn: Callable[[ProxySnapshot], float | int | None]


SENSORS: tuple[ProxySensorDescription, ...] = (
    ProxySensorDescription(
        key="last_advertisement",
        translation_key="last_advertisement",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.last_advertisement,
    ),
    ProxySensorDescription(
        key="connection_failures_1h",
        translation_key="connection_failures_1h",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.connection_failures_1h,
    ),
    ProxySensorDescription(
        key="connections_1h",
        translation_key="connections_1h",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.connections_1h,
    ),
    ProxySensorDescription(
        key="connections_in_progress",
        translation_key="connections_in_progress",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.connections_in_progress,
    ),
    ProxySensorDescription(
        key="devices_heard",
        translation_key="devices_heard",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.devices_heard,
    ),
)


def _entity_prefix(hass: HomeAssistant, device_id: str | None) -> str | None:
    """Reuse an ESPHome proxy's existing entity ID prefix, if it has one.

    ESPHome entity IDs keep the original node name even after a rename, so
    the restart button gives the prefix the rest of the board's entities use,
    e.g. button.esp32_bluetooth_proxy_a1b2c3_restart -> esp32_bluetooth_proxy_a1b2c3.
    Returns None otherwise, and Home Assistant names the entity from the device.
    """
    if device_id:
        for ent in er.async_entries_for_device(er.async_get(hass), device_id):
            if ent.platform == "esphome" and ent.entity_id.startswith("button."):
                object_id = ent.entity_id.split(".", 1)[1]
                if object_id.endswith("_restart"):
                    return object_id.removesuffix("_restart")
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProxyHealthConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors for every watched proxy, and for proxies added later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[ProxySensor] = []
        for proxy in coordinator.proxies():
            if proxy.source in known:
                continue
            known.add(proxy.source)
            prefix = _entity_prefix(hass, proxy.device_id)
            new.extend(
                ProxySensor(coordinator, proxy, prefix, desc) for desc in SENSORS
            )
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class ProxySensor(CoordinatorEntity[ProxyHealthCoordinator], SensorEntity):
    """A health figure for one proxy."""

    _attr_has_entity_name = True
    entity_description: ProxySensorDescription

    def __init__(
        self,
        coordinator: ProxyHealthCoordinator,
        proxy: ProxyInfo,
        prefix: str | None,
        description: ProxySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._source = proxy.source
        self._attr_unique_id = f"{proxy.source}_{description.key}"
        if prefix:
            # Only used the first time the entity is registered.
            self.entity_id = f"sensor.{prefix}_{description.key}"
        if proxy.device_id:
            # Link to the proxy's own device. Since 2026.x a DeviceInfo with
            # the same connections creates a separate (shadowed) device per
            # config entry instead of merging, so device_info must not be set.
            self.device_entry = dr.async_get(coordinator.hass).async_get(
                proxy.device_id
            )
        if self.device_entry is None:
            # No device to borrow a name from: name the entity after the source.
            self._attr_has_entity_name = False
            self._attr_name = (
                f"Bluetooth proxy {proxy.source} "
                + description.key.replace("_", " ").replace(" 1h", " (1 h)")
            )

    @property
    def _snapshot(self) -> ProxySnapshot | None:
        return (self.coordinator.data or {}).get(self._source)

    @property
    def available(self) -> bool:
        snap = self._snapshot
        return (
            super().available
            and snap is not None
            and snap.present
            and self.entity_description.value_fn(snap) is not None
        )

    @property
    def native_value(self) -> float | int | None:
        snap = self._snapshot
        return None if snap is None else self.entity_description.value_fn(snap)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        snap = self._snapshot
        if snap is None:
            return None
        key = self.entity_description.key
        if key == "last_advertisement":
            return {"source": self._source, "scanner": snap.name, "scanning": snap.scanning}
        if key in ("connection_failures_1h", "connections_1h"):
            # False for the first hour after Home Assistant starts.
            return {"window_complete": snap.window_complete}
        return None
