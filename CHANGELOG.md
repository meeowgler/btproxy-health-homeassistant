# Changelog

## 0.2.0 - 2026-10-04

- Watches every remote Bluetooth scanner (ESPHome, Shelly, ...), not only ESPHome.
- Entities without an ESPHome restart button take Home Assistant's default entity IDs.
- Ships its own icon (`brand/`).

## 0.1.1 - 2026-10-04

- Sensors attach to the proxy's existing device via `Entity.device_entry`. 0.1.0 used
  `DeviceInfo(connections=...)`, which since Home Assistant 2026.9 creates a separate
  device record instead of merging; 0.1.1 removes those records at startup.

## 0.1.0 - 2026-10-04

- First version: last advertisement, hourly connection failures and successes,
  connections in progress and devices heard, per proxy.
