"""Poll the Bluetooth integration's scanners and keep per-proxy health figures.

Public API used: bluetooth.async_scanner_by_source, BaseHaScanner.source/name/
scanning/connectable/discovered_devices/time_since_last_detection()/
connections_in_progress().

Private habluetooth counters used (no public accessor exists):
_connect_failed_total, _connect_completed_total. If a future habluetooth
renames them, those two sensors go unavailable and one error is logged; the
liveness sensor does not depend on them.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import logging
import time
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    BLUETOOTH_DOMAIN,
    CONF_SOURCE,
    CONF_SOURCE_CONFIG_ENTRY_ID,
    CONF_SOURCE_DEVICE_ID,
    CONF_SOURCE_DOMAIN,
    DOMAIN,
    FAILURE_WINDOW_SECONDS,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_PRIVATE_COUNTERS = ("_connect_failed_total", "_connect_completed_total")


@dataclass(slots=True)
class ProxyInfo:
    """A watched proxy, known from its bluetooth config entry."""

    source: str
    device_id: str | None


@dataclass(slots=True)
class ProxySnapshot:
    """One poll's figures for a proxy. None means not available."""

    present: bool = False
    last_advertisement: float | None = None
    connections_in_progress: int | None = None
    devices_heard: int | None = None
    connection_failures_1h: int | None = None
    connections_1h: int | None = None
    window_complete: bool = False
    scanning: bool | None = None
    name: str | None = None


@dataclass(slots=True)
class _CounterWindow:
    """Rolling one-hour sum of increments of a counter that can reset."""

    last_value: int | None = None
    last_scanner_id: int | None = None
    started: float = field(default_factory=time.monotonic)
    increments: deque[tuple[float, int]] = field(default_factory=deque)

    def add(self, now: float, scanner_id: int, value: int) -> None:
        if self.last_value is None:
            increment = 0  # first sample is the baseline, not an hour's worth
        elif scanner_id != self.last_scanner_id or value < self.last_value:
            # New scanner object (proxy reconnected) or counters cleared.
            increment = value
        else:
            increment = value - self.last_value
        self.last_value = value
        self.last_scanner_id = scanner_id
        if increment:
            self.increments.append((now, increment))
        cutoff = now - FAILURE_WINDOW_SECONDS
        while self.increments and self.increments[0][0] < cutoff:
            self.increments.popleft()

    def total(self) -> int:
        return sum(inc for _, inc in self.increments)

    def complete(self, now: float) -> bool:
        return now - self.started >= FAILURE_WINDOW_SECONDS


class ProxyHealthCoordinator(DataUpdateCoordinator[dict[str, ProxySnapshot]]):
    """Collect health figures for every remote Bluetooth proxy."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=True,
        )
        self._failed: dict[str, _CounterWindow] = {}
        self._completed: dict[str, _CounterWindow] = {}
        self._private_ok = True
        self._warned_unlinked: set[str] = set()

    def proxies(self) -> list[ProxyInfo]:
        """Return every watched proxy, whether or not it is connected now.

        The bluetooth integration keeps one config entry per remote scanner
        (unique_id = scanner source) that survives disconnects, so a frozen
        proxy is still listed here and its sensors go unavailable.
        """
        dev_reg = dr.async_get(self.hass)
        found: list[ProxyInfo] = []
        for entry in self.hass.config_entries.async_entries(BLUETOOTH_DOMAIN):
            data = entry.data
            # Remote scanners (ESPHome, Shelly, ...) carry their source domain;
            # local adapters do not and are not proxies.
            if not data.get(CONF_SOURCE_DOMAIN):
                continue
            source = data.get(CONF_SOURCE) or entry.unique_id
            if not source:
                continue
            device_id = data.get(CONF_SOURCE_DEVICE_ID)
            if not device_id or dev_reg.async_get(device_id) is None:
                device_id = None
                # Fall back to the source integration entry's only device.
                if src_entry_id := data.get(CONF_SOURCE_CONFIG_ENTRY_ID):
                    devices = dr.async_entries_for_config_entry(dev_reg, src_entry_id)
                    if len(devices) == 1:
                        device_id = devices[0].id
            if device_id is None and source not in self._warned_unlinked:
                self._warned_unlinked.add(source)
                _LOGGER.error(
                    "Bluetooth proxy %s (%s) has no linked device; its sensors "
                    "will not be attached to a device",
                    source,
                    entry.title,
                )
            found.append(ProxyInfo(source=source, device_id=device_id))
        return found

    def _read_private(self, scanner: Any) -> tuple[int, int] | None:
        if not self._private_ok:
            return None
        try:
            failed, completed = (int(getattr(scanner, n)) for n in _PRIVATE_COUNTERS)
        except (AttributeError, TypeError, ValueError):
            self._private_ok = False
            _LOGGER.error(
                "habluetooth no longer exposes %s on %s; the connection "
                "count sensors are unavailable until this integration is updated",
                " / ".join(_PRIVATE_COUNTERS),
                type(scanner).__name__,
            )
            return None
        return failed, completed

    async def _async_update_data(self) -> dict[str, ProxySnapshot]:
        now = time.monotonic()
        result: dict[str, ProxySnapshot] = {}
        for proxy in self.proxies():
            source = proxy.source
            snap = ProxySnapshot()
            result[source] = snap
            scanner = bluetooth.async_scanner_by_source(self.hass, source)
            if scanner is None:
                continue  # disconnected: every sensor unavailable
            snap.present = True
            snap.name = scanner.name
            snap.scanning = scanner.scanning
            snap.last_advertisement = round(scanner.time_since_last_detection(), 1)
            snap.connections_in_progress = scanner.connections_in_progress()
            snap.devices_heard = len(scanner.discovered_devices)

            counters = self._read_private(scanner)
            if counters is None:
                continue
            failed, completed = counters
            fw = self._failed.setdefault(source, _CounterWindow())
            cw = self._completed.setdefault(source, _CounterWindow())
            fw.add(now, id(scanner), failed)
            cw.add(now, id(scanner), completed)
            snap.connection_failures_1h = fw.total()
            snap.connections_1h = cw.total()
            snap.window_complete = fw.complete(now)
        return result
