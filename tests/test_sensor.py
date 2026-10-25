"""Tests for sensor state and attribute plumbing."""

import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.hdhomerun.const import (
    CONF_DATA_COORDINATOR_GENERAL,
    CONF_DATA_COORDINATOR_TUNER_STATUS,
    CONF_EPG_PROXY,
    DOMAIN,
)
from custom_components.hdhomerun.epg import EPGProxy
from custom_components.hdhomerun.pyhdhr.const import DiscoverMode
from custom_components.hdhomerun.sensor import (
    AdditionalSensorDescription,
    EPGDiagnostic,
    HDHomerunSensor,
    HDHomerunTunerSensor,
    async_setup_entry,
)

ENTRY = SimpleNamespace(unique_id="1234ABCD", options={})


def test_tuner_sensor_writes_current_poll():
    """The state written on a coordinator update reflects that update."""
    device = SimpleNamespace(tuner_status=[{"Resource": "tuner0"}])
    coordinator = SimpleNamespace(data=device, last_update_success=True)
    sensor = HDHomerunTunerSensor(
        config_entry=ENTRY,
        coordinator=coordinator,
        device_name="Tuner0",
        description=SensorEntityDescription(key="VctNumber", name="Tuner0 Channel"),
    )
    written = []
    sensor.async_write_ha_state = lambda: written.append(sensor.native_value)
    device.tuner_status = [{"Resource": "tuner0", "VctNumber": "7.1"}]
    sensor._handle_coordinator_update()
    assert written == ["7.1"]


def test_device_sensor_exposes_extra_attributes():
    """Additional descriptions' attributes reach the entity (e.g. channel lists)."""
    device = SimpleNamespace(
        channels=[{"GuideName": "KOMO", "Favorite": 1}, {"GuideName": "KING"}]
    )
    sensor = HDHomerunSensor(
        additional_description=AdditionalSensorDescription(
            extra_attributes=lambda d: {
                "channels": [c["GuideName"] for c in d.channels if c.get("Favorite") == 1]
            },
            state_value=lambda d: len([c for c in d if c.get("Favorite") == 1]),
        ),
        config_entry=ENTRY,
        coordinator=SimpleNamespace(data=device),
        description=SensorEntityDescription(key="channels", name="Favourite Channels"),
    )
    assert sensor.native_value == 1
    assert sensor.extra_state_attributes == {"channels": ["KOMO"]}


@pytest.mark.asyncio
async def test_epg_freshness_timestamps_follow_cached_snapshot(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    await er.async_load(hass)
    entry = SimpleNamespace(unique_id="1234ABCD", entry_id="entry", options={})
    proxy = EPGProxy(hass, entry.entry_id, "192.0.2.1", 6)
    coordinator = SimpleNamespace(data=SimpleNamespace(
        discovery_method=DiscoverMode.HTTP, tuner_status=[],
    ))
    entry_data = {
        CONF_DATA_COORDINATOR_GENERAL: coordinator,
        CONF_DATA_COORDINATOR_TUNER_STATUS: coordinator,
    }
    hass.data[DOMAIN] = {entry.entry_id: entry_data}
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    assert not any(isinstance(entity, EPGDiagnostic) for entity in entities)

    entry_data[CONF_EPG_PROXY] = proxy
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    diagnostics = [entity for entity in entities if isinstance(entity, EPGDiagnostic)]
    assert len(diagnostics) == 4
    platform = EntityPlatform(
        hass=hass, logger=logging.getLogger(__name__), domain="sensor",
        platform_name=DOMAIN, platform=None, scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    platform.async_prepare()
    try:
        await platform.async_add_entities(diagnostics)
        updated, coverage, failures, last_failure = diagnostics
        assert hass.states.get(updated.entity_id).state == "unknown"
        assert hass.states.get(coverage.entity_id).state == "unknown"
        assert hass.states.get(failures.entity_id).state == "0"
        assert hass.states.get(last_failure.entity_id).state == "unknown"

        # A cached guide can have an old fetch time and a different coverage end.
        proxy.fetched_at = "2026-10-23T09:15:00-05:00"
        proxy.summary = {"coverage_end": "2026-10-27T21:30:00-05:00"}
        proxy.notify()
        assert hass.states.get(updated.entity_id).state == "2026-10-23T14:15:00+00:00"
        assert hass.states.get(coverage.entity_id).state == "2026-10-28T02:30:00+00:00"
        assert all(hass.states.get(entity.entity_id).attributes["device_class"] == "timestamp"
                   for entity in (updated, coverage, last_failure))

        proxy.error = "TimeoutError"
        proxy.consecutive_failures = 2
        proxy.last_failure = "2026-10-25T10:45:00-05:00"
        proxy.notify()
        assert hass.states.get(updated.entity_id).state == "2026-10-23T14:15:00+00:00"
        assert hass.states.get(coverage.entity_id).state == "2026-10-28T02:30:00+00:00"
        assert hass.states.get(failures.entity_id).state == "2"
        assert hass.states.get(last_failure.entity_id).state == "2026-10-25T15:45:00+00:00"

        proxy.fetched_at = "2026-10-25T16:00:00+00:00"
        proxy.summary = {"coverage_end": "2026-10-30T00:00:00+00:00"}
        proxy.error = None
        proxy.consecutive_failures = 0
        proxy.notify()
        assert hass.states.get(updated.entity_id).state == "2026-10-25T16:00:00+00:00"
        assert hass.states.get(coverage.entity_id).state == "2026-10-30T00:00:00+00:00"
        assert hass.states.get(failures.entity_id).state == "0"
        assert hass.states.get(last_failure.entity_id).state == "2026-10-25T15:45:00+00:00"
    finally:
        await platform.async_reset()
        await hass.async_stop()
