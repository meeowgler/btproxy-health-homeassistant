"""Constants for Bluetooth Proxy Health."""

from datetime import timedelta

DOMAIN = "btproxy_health"
BLUETOOTH_DOMAIN = "bluetooth"

UPDATE_INTERVAL = timedelta(seconds=60)
FAILURE_WINDOW_SECONDS = 3600

# Keys the bluetooth integration stores on each remote scanner's config entry
# (homeassistant/components/bluetooth/const.py).
CONF_SOURCE = "source"
CONF_SOURCE_DOMAIN = "source_domain"
CONF_SOURCE_CONFIG_ENTRY_ID = "source_config_entry_id"
CONF_SOURCE_DEVICE_ID = "source_device_id"
