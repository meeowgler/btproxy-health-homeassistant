"""Config flow for Bluetooth Proxy Health (single instance, no options)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class ProxyHealthConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single entry after a confirm step."""
        if user_input is not None:
            return self.async_create_entry(title="Bluetooth Proxy Health", data={})
        return self.async_show_form(step_id="user")
