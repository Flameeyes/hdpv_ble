"""Config flow for Hunter Douglas PowerView (BLE) integration."""

from dataclasses import dataclass
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import UUID_COV_SERVICE as UUID
from .const import CONF_HOME_KEY, DOMAIN, LOGGER, MFCT_ID

# Regex for validating hex-encoded home key (exactly 32 hex chars = 16 bytes)
HOME_KEY_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def _validate_home_key(value: str) -> str:
    """Validate and normalize a home key hex string."""
    cleaned = value.strip().replace(" ", "").replace(":", "").replace("-", "")
    if not HOME_KEY_PATTERN.match(cleaned):
        raise vol.Invalid(
            "Home key must be exactly 32 hex characters (16 bytes). "
            "Example: 000102030405060708090a0b0c0d0e0f"
        )
    return cleaned.lower()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hunter Douglas PowerView (BLE)."""

    VERSION = 2
    MINOR_VERSION = 0

    @dataclass
    class DiscoveredDevice:
        """A discovered bluetooth device."""

        name: str
        discovery_info: BluetoothServiceInfoBleak

    def __init__(self) -> None:
        """Initialize the config flow."""

        self._discovered_device: ConfigFlow.DiscoveredDevice | None = None
        self._discovered_devices: dict[str, ConfigFlow.DiscoveredDevice] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler."""
        return PVOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a flow initialized by Bluetooth discovery."""
        LOGGER.debug("Bluetooth device detected: %s", discovery_info)

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovered_device = ConfigFlow.DiscoveredDevice(
            discovery_info.name, discovery_info
        )
        self.context["title_placeholders"] = {"name": self._discovered_device.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm bluetooth device discovery and collect home key."""
        assert self._discovered_device is not None
        LOGGER.debug("confirm step for %s", self._discovered_device.name)

        errors: dict[str, str] = {}

        if user_input is not None:
            home_key_hex = user_input.get(CONF_HOME_KEY, "").strip()
            if home_key_hex:
                try:
                    home_key_hex = _validate_home_key(home_key_hex)
                except vol.Invalid:
                    errors[CONF_HOME_KEY] = "invalid_home_key"

            if not errors:
                return self.async_create_entry(
                    title=self._discovered_device.name,
                    data={
                        "manufacturer_data": self._discovered_device.discovery_info.manufacturer_data[
                            MFCT_ID
                        ].hex(),
                        CONF_HOME_KEY: home_key_hex,
                    },
                )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovered_device.name},
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_HOME_KEY, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        LOGGER.debug("user step")

        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            home_key_hex = user_input.get(CONF_HOME_KEY, "").strip()

            if home_key_hex:
                try:
                    home_key_hex = _validate_home_key(home_key_hex)
                except vol.Invalid:
                    errors[CONF_HOME_KEY] = "invalid_home_key"

            if not errors:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                self._discovered_device = self._discovered_devices[address]

                self.context["title_placeholders"] = {
                    "name": self._discovered_device.name
                }

                return self.async_create_entry(
                    title=self._discovered_device.name,
                    data={
                        "manufacturer_data": self._discovered_device.discovery_info.manufacturer_data[
                            MFCT_ID
                        ].hex(),
                        CONF_HOME_KEY: home_key_hex,
                    },
                )

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue

            if MFCT_ID not in discovery_info.manufacturer_data:
                continue

            if UUID not in discovery_info.service_uuids:
                continue

            self._discovered_devices[address] = ConfigFlow.DiscoveredDevice(
                discovery_info.name, discovery_info
            )

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        titles: list[SelectOptionDict] = []
        for address, discovery in self._discovered_devices.items():
            titles.append({"value": address, "label": discovery.name})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): SelectSelector(
                        SelectSelectorConfig(options=titles)
                    ),
                    vol.Optional(CONF_HOME_KEY, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )


class PVOptionsFlow(OptionsFlow):
    """Handle options flow for Hunter Douglas PowerView (BLE)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial options step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            home_key_hex = user_input.get(CONF_HOME_KEY, "").strip()
            if home_key_hex:
                try:
                    home_key_hex = _validate_home_key(home_key_hex)
                except vol.Invalid:
                    errors[CONF_HOME_KEY] = "invalid_home_key"

            if not errors:
                # Update the config entry data with the new key
                new_data = {**self.config_entry.data, CONF_HOME_KEY: home_key_hex}
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                # Reload the integration to pick up the new key
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(title="", data={})

        current_key = self.config_entry.data.get(CONF_HOME_KEY, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_HOME_KEY, default=current_key): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )
