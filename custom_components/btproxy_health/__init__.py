"""Bluetooth Proxy Health: per-proxy liveness from the Bluetooth integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .coordinator import ProxyHealthCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type ProxyHealthConfigEntry = ConfigEntry[ProxyHealthCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ProxyHealthConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = ProxyHealthCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _remove_own_devices(hass, entry)
    return True


def _remove_own_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop device records owned by this entry.

    The sensors attach to the proxies' own devices, so this entry should own no
    devices. Version 0.1.0 created a duplicate per proxy; remove any such
    record once none of this integration's entities still point at it.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        still_used = [
            ent.entity_id
            for ent in er.async_entries_for_device(
                ent_reg, device.id, include_disabled_entities=True
            )
            if ent.config_entry_id == entry.entry_id
        ]
        if still_used:
            _LOGGER.error(
                "Not removing device %s: still used by %s", device.id, still_used
            )
            continue
        dev_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
        _LOGGER.info("Removed duplicate device record %s (%s)", device.id, device.name)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a leftover device record from the UI."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ProxyHealthConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
