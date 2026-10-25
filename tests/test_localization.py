"""Regression coverage for native localization without registry ID migrations."""

import json
import logging
from datetime import timedelta
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.hdhomerun import binary_sensor, button, select, sensor, update
from custom_components.hdhomerun.button import EPGButton, LineupButton
from custom_components.hdhomerun.const import (
    CONF_DATA_COORDINATOR_GENERAL,
    CONF_DATA_COORDINATOR_TUNER_STATUS,
    CONF_EPG_PROXY,
    DOMAIN,
)
from custom_components.hdhomerun.pyhdhr.const import DiscoverMode
from custom_components.hdhomerun.sensor import EPGStatus, HDHomerunSensor, HDHomerunTunerSensor

TRANSLATIONS = Path(__file__).parents[1] / "custom_components/hdhomerun/translations"


def translations(language):
    """Load the same flattened entity translations consumed by HA platforms."""
    data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
    return {
        f"component.hdhomerun.entity.{domain}.{key}.name": value["name"]
        for domain, entities in data["entity"].items()
        for key, value in entities.items()
        if "name" in value
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("language,favourite,programme", [
    ("en", "Favorite Channels", "Program"),
    ("en-GB", "Favourite Channels", "Programme"),
])
async def test_localized_names_keep_legacy_ids_and_user_names(tmp_path, monkeypatch, language, favourite, programme):
    """Local spelling must not change old or newly generated entity IDs."""
    hass = HomeAssistant(str(tmp_path))
    hass.config.language = language
    hass.config_entries = ConfigEntries(hass, {})
    # Do not invoke discovery/network setup; platform registration remains real.
    monkeypatch.setattr(hass.config_entries, "async_setup", AsyncMock(return_value=True))
    await er.async_load(hass)
    await dr.async_load(hass)
    registry = er.async_get(hass)
    entry = ConfigEntry(
        domain=DOMAIN, unique_id="1234ABCD", options={}, data={}, title="My HDHomeRun",
        version=1, minor_version=1, source="user", discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    await hass.config_entries.async_add(entry)
    coordinator = DataUpdateCoordinator(hass, logging.getLogger(__name__), name="offline", config_entry=entry)
    coordinator.async_set_updated_data(SimpleNamespace(
        tuner_status=[{"Resource": "tuner0"}], channels=[], model="HDHR",
        base_url="http://192.0.2.1", discovery_method=DiscoverMode.HTTP,
        installed_version="20261001",
    ))
    platform = EntityPlatform(
        hass=hass, logger=logging.getLogger(__name__), domain="sensor",
        platform_name=DOMAIN, platform=None, scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    platform.config_entry = entry
    platform.async_prepare()
    platform.platform_data.platform_translations = translations(language)
    platform.platform_data.object_id_platform_translations = translations(language)
    # Seed a user-customized entity; its ID/name must win over localization.
    registry.async_get_or_create(
        "sensor", DOMAIN, "1234ABCD::sensor::tuner0_frequency",
        suggested_object_id="living_room_rf",
    )
    registry.async_update_entity("sensor.living_room_rf", name="My aerial")
    descriptions = [
        SensorEntityDescription(key="channels", name="Favourite Channels", translation_key="fav_channels"),
        SensorEntityDescription(key="", name="Tuner0 Programme", translation_key="tuner_programme"),
        SensorEntityDescription(key="Frequency", name="Tuner0 Frequency", translation_key="tuner_frequency"),
        SensorEntityDescription(key="", name="Tuner0", translation_key="tuner_status"),
    ]
    entities = [HDHomerunSensor(config_entry=entry, coordinator=coordinator, description=descriptions[0])]
    entities.extend(HDHomerunTunerSensor(
        config_entry=entry, coordinator=coordinator, device_name="Tuner0", description=description,
    ) for description in descriptions[1:])
    # Real coordinator and registry, with offline device data and no polling.
    for entity in entities:
        entity._attr_should_poll = False
    try:
        await platform.async_add_entities(entities)
        assert entities[0].name == favourite
        assert entities[1].name == programme
        assert entities[1].has_entity_name
        assert entities[3].name is None
        assert [entity.unique_id for entity in entities] == [
            "1234ABCD::sensor::favourite_channels", "1234ABCD::sensor::tuner0_programme",
            "1234ABCD::sensor::tuner0_frequency", "1234ABCD::sensor::tuner0",
        ]
        assert [entity.entity_id for entity in entities] == [
            "sensor.my_hdhomerun_favourite_channels", "sensor.tuner0_programme",
            "sensor.living_room_rf", "sensor.tuner0",
        ]
        assert hass.states.get("sensor.tuner0_programme").attributes["friendly_name"] == f"Tuner0 {programme}"
        assert hass.states.get("sensor.tuner0").attributes["friendly_name"] == "Tuner0"
        assert hass.states.get("sensor.living_room_rf").attributes["friendly_name"] == "My aerial"
        tuner_device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "1234ABCD_Tuner0")})
        dr.async_get(hass).async_update_device(tuner_device.id, name_by_user="Roof tuner")
        await hass.async_block_till_done()
        assert hass.states.get("sensor.tuner0_programme").attributes["friendly_name"] == f"Roof tuner {programme}"
        assert hass.states.get("sensor.living_room_rf").attributes["friendly_name"] == "My aerial"
        new_sensor = HDHomerunTunerSensor(
            config_entry=entry, coordinator=coordinator, device_name="Tuner0",
            description=SensorEntityDescription(key="SignalQualityPercent", name="Tuner0 Signal Quality", translation_key="tuner_signal_quality"),
        )
        await platform.async_add_entities([new_sensor])
        assert new_sensor.entity_id == "sensor.tuner0_signal_quality"
        assert hass.states.get(new_sensor.entity_id).attributes["friendly_name"] == "Roof tuner Signal Quality"
    finally:
        await platform.async_reset()
        await hass.async_stop()


def test_epg_status_is_translatable_enum():
    """Guide states are stable machine values with translated UI labels."""
    sensor = EPGStatus(SimpleNamespace(unique_id="1234ABCD"), SimpleNamespace(xml=None))
    assert sensor.device_class == SensorDeviceClass.ENUM
    assert sensor.options == ["empty", "expired", "refresh_failed", "ready"]
    assert sensor.native_value == "empty"
    for language in ("en", "en-GB"):
        data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
        assert set(data["entity"]["sensor"]["epg_status"]["state"]) == set(sensor.options)
        assert "host" in data["config"]["step"]["select_device"]["data"]
        assert "epg_enabled" in data["options"]["step"]["options"]["data"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["epg", "lineup"])
async def test_refresh_errors_have_native_translations(kind):
    """Failed service actions expose translated errors, not only hardcoded prose."""
    entry = SimpleNamespace(unique_id="1234ABCD", options={})
    if kind == "epg":
        entity = EPGButton(entry, SimpleNamespace(refresh=AsyncMock(return_value=False)), "refresh")
    else:
        entity = LineupButton(
            config_entry=entry,
            coordinator=SimpleNamespace(
                data=SimpleNamespace(lineup_fetched_at=None, async_get_lineup_http=AsyncMock()),
                async_update_listeners=lambda: None,
            ),
            description=ButtonEntityDescription(key="", name="Refresh Lineup", translation_key="refresh_lineup"),
        )
    with pytest.raises(HomeAssistantError) as raised:
        await entity.async_press()
    assert raised.value.translation_domain == DOMAIN
    assert raised.value.translation_key == f"{kind}_refresh_failed"
    for language in ("en", "en-GB"):
        data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
        assert data["exceptions"][raised.value.translation_key]["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_firmware", [False, True])
async def test_every_native_entity_has_both_english_translations(tmp_path, monkeypatch, legacy_firmware):
    """Actual platform factories must wire every display name to a translated key."""
    hass = HomeAssistant(str(tmp_path))
    await er.async_load(hass)
    entry = SimpleNamespace(unique_id="1234ABCD", entry_id="entry", options={})
    coordinator = SimpleNamespace(data=SimpleNamespace(
        discovery_method=DiscoverMode.HTTP, tuner_status=[{"Resource": "tuner0"}],
        channel_sources=["Antenna", "Cable"],
    ))
    hass.data[DOMAIN] = {entry.entry_id: {
        CONF_DATA_COORDINATOR_GENERAL: coordinator,
        CONF_DATA_COORDINATOR_TUNER_STATUS: coordinator,
        CONF_EPG_PROXY: SimpleNamespace(),
    }}
    if legacy_firmware:
        monkeypatch.setattr(sensor, "UPDATE_DOMAIN", None)
        monkeypatch.setattr(binary_sensor, "UPDATE_DOMAIN", None)
    try:
        for module, domain in ((sensor, "sensor"), (binary_sensor, "binary_sensor"),
                               (button, "button"), (select, "select"), (update, "update")):
            entities = []

            def collect(new_entities, **kwargs):
                entities.extend(new_entities)

            await module.async_setup_entry(hass, entry, collect)
            assert entities
            for entity in entities:
                assert entity.has_entity_name
                assert entity.translation_key
                for language in ("en", "en-GB"):
                    data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
                    translated = data["entity"][domain][entity.translation_key]
                    if entity.translation_key == "tuner_status":
                        assert set(translated["state"]) == {"idle", "in_use", "scanning"}
                    else:
                        assert translated["name"]
    finally:
        await hass.async_stop()
