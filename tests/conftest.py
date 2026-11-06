"""Shared Home Assistant initialization for real platform tests."""

from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


@pytest_asyncio.fixture
async def hass(tmp_path):
    """Load config entries before registries, as HA's bootstrap does."""
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    # Older HA initializes the device registry lazily in async_get.
    if hasattr(dr, "async_setup"):
        dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)
    try:
        yield hass
    finally:
        await hass.async_stop()


@pytest_asyncio.fixture
async def config_entry(hass):
    """Register an offline entry without invoking receiver discovery."""
    entry = ConfigEntry(
        domain="hdhomerun", unique_id="1234ABCD", options={},
        data={"host": "192.0.2.1"}, title="My HDHomeRun",
        version=1, minor_version=1, source="user", discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    with patch.object(hass.config_entries, "async_setup", AsyncMock(return_value=True)):
        await hass.config_entries.async_add(entry)
    return entry
