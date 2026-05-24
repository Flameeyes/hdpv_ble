"""The Hunter Douglas PowerView (BLE) integration.

@author: patman15
@license: Apache-2.0 license
"""

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import CONF_HOME_KEY, LOGGER
from .coordinator import PVCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.SENSOR,
    Platform.BUTTON,
]

type ConfigEntryType = ConfigEntry[PVCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntryType) -> bool:
    """Set up BT Battery Management System from a config entry."""
    LOGGER.debug("Setup of %s", repr(entry))

    if entry.unique_id is None:
        raise ConfigEntryError("Missing unique ID for device.")

    ble_device: BLEDevice | None = async_ble_device_from_address(
        hass=hass, address=entry.unique_id, connectable=True
    )

    if not ble_device:
        raise ConfigEntryNotReady(
            f"Could not find PowerView device ({entry.unique_id}) via Bluetooth"
        )

    coordinator = PVCoordinator(hass, ble_device, entry.data.copy())
    try:
        await coordinator.query_dev_info()
    except BleakError as err:
        raise ConfigEntryNotReady("Unable to query device info.") from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntryType) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    LOGGER.debug("Unloaded config entry: %s, ok? %s!", entry.unique_id, str(unload_ok))
    return unload_ok


async def async_migrate_entry(
    _hass: HomeAssistant, config_entry: ConfigEntryType
) -> bool:
    """Migrate old entry."""

    if config_entry.version > 2:
        # This means the user has downgraded from a future version
        LOGGER.debug("Cannot downgrade from version %s", config_entry.version)
        return False

    if config_entry.version == 1:
        LOGGER.debug("Migrating from version 1 to 2")
        # V1 -> V2: add empty home_key to existing entries.
        # Users will need to set the key via the options flow.
        new_data = {**config_entry.data}
        if CONF_HOME_KEY not in new_data:
            new_data[CONF_HOME_KEY] = ""
        _hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=2, minor_version=0
        )
        LOGGER.info(
            "Migrated config entry %s to v2. Set your home_key in "
            "Settings > Devices > PowerView > Configure.",
            config_entry.unique_id,
        )

    return True
