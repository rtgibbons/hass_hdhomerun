"""Refresh buttons share their action and timestamp with automatic fetches."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from homeassistant.components import button
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.hdhomerun import _async_press_refresh_button, epg
from custom_components.hdhomerun.button import EPGButton, LineupButton
from custom_components.hdhomerun.const import DOMAIN
from custom_components.hdhomerun.pyhdhr.const import DiscoverMode


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["epg", "lineup"])
async def test_automatic_refresh_updates_button_timestamp(tmp_path, kind):
    hass = HomeAssistant(str(tmp_path))
    await er.async_load(hass)
    await button.async_setup(hass, {})
    platform = EntityPlatform(
        hass=hass, logger=logging.getLogger(__name__), domain="button",
        platform_name=DOMAIN, platform=None, scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    platform.async_prepare()
    entry = SimpleNamespace(unique_id="1234ABCD", options={})
    refreshed = []

    async def fetch():
        refreshed.append(datetime.now(timezone.utc))
        device.lineup_fetched_at = refreshed[-1]
        return True

    device = SimpleNamespace(
        lineup_fetched_at=None, async_get_lineup_http=fetch,
        base_url="http://192.0.2.1", discovery_method=DiscoverMode.HTTP,
        model="HDHR", name="Test tuner", installed_version="20260101",
    )
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name="test", config_entry=None
    )
    coordinator.async_set_updated_data(device)
    proxy = epg.EPGProxy(hass, "entry", "192.0.2.1", 6)
    proxy.refresh = fetch
    if kind == "epg":
        entity = EPGButton(entry, proxy, "refresh")
    else:
        entity = LineupButton(
            config_entry=entry, coordinator=coordinator,
            description=ButtonEntityDescription(key="", name="Refresh Lineup"),
        )
    try:
        await platform.async_add_entities([entity])
        registry = er.async_get(hass)
        # A renamed entity must still be found by its stable unique ID.
        registry.async_update_entity(entity.entity_id, new_entity_id="button.renamed_refresh")
        await hass.async_block_till_done()
        entity_id = "button.renamed_refresh"
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
        manual = hass.states.get(entity_id).state
        await _async_press_refresh_button(hass, entity.unique_id, fetch)
        automatic = hass.states.get(entity_id).state
        assert datetime.fromisoformat(automatic) > datetime.fromisoformat(manual)
        assert len(refreshed) == 2

        registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        await hass.async_block_till_done()
        await _async_press_refresh_button(hass, entity.unique_id, fetch)
        assert len(refreshed) == 3
    finally:
        await platform.async_reset()
        await hass.async_stop()


@pytest.mark.asyncio
async def test_scheduled_refresh_continues_after_button_failure(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    proxy = epg.EPGProxy(hass, "entry", "192.0.2.1", 6)
    attempts = []
    retried = asyncio.Event()

    async def refresh():
        attempts.append(True)
        if len(attempts) == 1:
            raise HomeAssistantError("Fetch failed")
        retried.set()

    async def sleep(_):
        if retried.is_set():
            await asyncio.Event().wait()

    monkeypatch.setattr(epg, "asyncio", SimpleNamespace(
        sleep=sleep, CancelledError=asyncio.CancelledError,
    ))
    try:
        proxy.start(refresh)
        await asyncio.wait_for(retried.wait(), timeout=5)
        assert len(attempts) == 2
    finally:
        proxy.stop()
        await hass.async_block_till_done()
        await hass.async_stop()
