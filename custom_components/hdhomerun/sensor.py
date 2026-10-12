"""Sensors."""

# region #-- imports --#
from __future__ import annotations

import dataclasses
import logging
import os.path
import re
from collections.abc import Mapping
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Callable

from homeassistant.components.sensor import DOMAIN as ENTITY_DOMAIN
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    StateType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfDataRate, UnitOfFrequency
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import HDHomerunEntity, HDHomerunTunerEntity, entity_cleanup
from .const import (
    CONF_DATA_COORDINATOR_GENERAL,
    CONF_DATA_COORDINATOR_TUNER_STATUS,
    CONF_EPG_PROXY,
    CONF_TUNER_CHANNEL_ENTITY_PICTURE_PATH,
    CONF_TUNER_CHANNEL_FORMAT,
    CONF_TUNER_CHANNEL_NAME,
    CONF_TUNER_CHANNEL_NUMBER,
    CONF_TUNER_CHANNEL_NUMBER_NAME,
    DEF_TUNER_CHANNEL_ENTITY_PICTURE_PATH,
    DEF_TUNER_CHANNEL_FORMAT,
    DOMAIN,
    UPDATE_DOMAIN,
)
from .pyhdhr.const import DiscoverMode
from .pyhdhr.discover import HDHomeRunDevice
from .epg import EPGProxy

# endregion

_LOGGER = logging.getLogger(__name__)


class EPGStatus(SensorEntity):
    """Guide health and UHF URL for an authenticated HA user."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, proxy: EPGProxy) -> None:
        """Bind the status entity to the entry's cache."""
        self.entry = entry
        self.proxy = proxy
        self._attr_unique_id = f"{entry.unique_id}::epg::status"
        self._attr_translation_key = "epg_status"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.unique_id)}}

    async def async_added_to_hass(self) -> None:
        """Listen for snapshot and token changes."""
        self.proxy.listeners.append(self.async_write_ha_state)
        self.async_on_remove(lambda: self.proxy.listeners.remove(self.async_write_ha_state))

    @property
    def native_value(self) -> str:
        """Show whether the cached guide is present and still covers now."""
        if not self.proxy.xml:
            return "empty"
        if datetime.fromisoformat(self.proxy.summary["coverage_end"]) < datetime.now(timezone.utc):
            return "expired"
        return "refresh_failed" if self.proxy.error else "ready"

    @property
    def extra_state_attributes(self) -> dict:
        """Expose URLs, cache age, coverage and lineup-to-XMLTV ID matches."""
        proxy = self.proxy
        base = self.hass.config.external_url or self.hass.config.internal_url or ""
        path = f"/api/hdhomerun/xmltv/{proxy.token}"
        attrs = {
            "url": f"{base.rstrip('/')}{path}",
            "gzip_url": f"{base.rstrip('/')}{path}.xml.gz",
            "m3u_url": f"{base.rstrip('/')}/api/hdhomerun/m3u/{proxy.token}",
            "fetched_at": proxy.fetched_at,
            "cache_age_hours": round((datetime.now(timezone.utc) - datetime.fromisoformat(proxy.fetched_at)).total_seconds() / 3600, 2) if proxy.fetched_at else None,
            "last_error_type": proxy.error,
            **proxy.summary,
        }
        device = self.hass.data[DOMAIN][self.entry.entry_id][CONF_DATA_COORDINATOR_GENERAL].data
        lineup = device.channels or []
        unmatched = [f"{channel.get('GuideNumber', '?')} {channel.get('GuideName', '')}" for channel in lineup
                     if proxy.index.match(channel.get("GuideNumber"), channel.get("GuideName")) is None]
        attrs["lineup_channels"] = len(lineup)
        attrs["lineup_name_matches"] = len(lineup) - len(unmatched)
        attrs["unmatched_lineup_examples"] = unmatched[:20]
        return attrs


# region #-- sensor descriptions --#
@dataclasses.dataclass(frozen=True)
class AdditionalSensorDescription:
    """Represent additional options for the button entity."""

    entity_picture: Callable | None = None
    extra_attributes: Callable | None = None
    state_value: Callable[[Any], Any] | None = None


# endregion


class TunerStates(StrEnum):
    """Possible states for the tuner."""

    IDLE = "idle"
    IN_USE = "in_use"
    SCANNING = "scanning"


def _get_status_entity_esa(tuner: dict[str, Any]) -> dict[str, Any]:
    """Generate the extra attributes for the status sensor."""
    regex = re.compile(r"(?<!^)(?=[A-Z])")
    ret = {
        regex.sub("_", k).lower().replace("_i_p", "_ip"): v
        for k, v in tuner.items()
        if k.lower() != "resource"
    }

    return ret


def _get_status_entity_picture(tuner: dict[str, Any], config: dict[str, Any]) -> str:
    """Get the entity picture based on configured paths."""
    ret = None
    picture_path: str = config.options.get(
        CONF_TUNER_CHANNEL_ENTITY_PICTURE_PATH,
        DEF_TUNER_CHANNEL_ENTITY_PICTURE_PATH,
    )
    if picture_path and _get_tuner_state(tuner, config) not in (
        TunerStates.IDLE,
        TunerStates.IN_USE,
        TunerStates.SCANNING,
    ):
        ret = os.path.join(picture_path, f"{tuner.get('VctName', '').lower()}.png")

    return ret


def _get_tuner_state(tuner: dict[str, Any], config: dict[str, Any]) -> str:
    """Calculate the status for the tuner."""
    ret = TunerStates.IDLE
    channel_format: str = config.options.get(
        CONF_TUNER_CHANNEL_FORMAT, DEF_TUNER_CHANNEL_FORMAT
    )
    if tuner.get("VctNumber") and tuner.get("VctName"):
        if channel_format == CONF_TUNER_CHANNEL_NAME:
            ret = tuner.get("VctName")
        elif channel_format == CONF_TUNER_CHANNEL_NUMBER:
            ret = tuner.get("VctNumber")
        elif channel_format == CONF_TUNER_CHANNEL_NUMBER_NAME:
            ret = f"{tuner.get('VctNumber')}: {tuner.get('VctName')}"
        else:
            ret = None
    elif tuner.get("TargetIP"):
        ret = TunerStates.IN_USE

    return ret


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the sensor."""
    coordinator_general: DataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ][CONF_DATA_COORDINATOR_GENERAL]
    coordinator_tuner: DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        CONF_DATA_COORDINATOR_TUNER_STATUS
    ]

    sensors: list = []
    sensors_to_remove: list[HDHomerunSensor] = []

    if (proxy := hass.data[DOMAIN][config_entry.entry_id].get(CONF_EPG_PROXY)) is not None:
        sensors.append(EPGStatus(config_entry, proxy))

    # region #-- add version sensors if need be --#
    if UPDATE_DOMAIN is None:
        sensors.extend(
            [
                HDHomerunSensor(
                    config_entry=config_entry,
                    coordinator=coordinator_general,
                    description=SensorEntityDescription(
                        key="current_firmware",
                        name="Version",
                    ),
                ),
                HDHomerunSensor(
                    additional_description=AdditionalSensorDescription(
                        state_value=lambda d: d.latest_firmware or d.current_firmware,
                    ),
                    config_entry=config_entry,
                    coordinator=coordinator_general,
                    description=SensorEntityDescription(
                        key="",
                        name="Newest Version",
                    ),
                ),
            ]
        )
    else:  # remove the existing version sensors if the update entity is available
        sensors_to_remove.extend(
            [
                HDHomerunSensor(
                    config_entry=config_entry,
                    coordinator=coordinator_general,
                    description=SensorEntityDescription(
                        key="current_firmware",
                        name="Version",
                    ),
                ),
                HDHomerunSensor(
                    config_entry=config_entry,
                    coordinator=coordinator_general,
                    description=SensorEntityDescription(
                        key="",
                        name="Newest Version",
                    ),
                ),
            ]
        )
    # endregion

    # region #-- add tuner sensors --#
    hdhomerun_device: HDHomeRunDevice | None = coordinator_tuner.data
    if hdhomerun_device is not None:
        for tuner in hdhomerun_device.tuner_status:
            device_name: str = tuner.get("Resource").title()
            if proxy is not None:
                sensors.append(
                    HDHomerunTunerProgrammeSensor(
                        proxy=proxy,
                        config_entry=config_entry,
                        coordinator=coordinator_tuner,
                        device_name=device_name,
                        description=SensorEntityDescription(
                            key="",
                            name=f"{device_name} Programme",
                            translation_key="tuner_programme",
                        ),
                    )
                )
            sensors.extend(
                [
                    HDHomerunTunerSensor(
                        additional_description=AdditionalSensorDescription(
                            entity_picture=_get_status_entity_picture,
                            extra_attributes=_get_status_entity_esa,
                            state_value=_get_tuner_state,
                        ),
                        config_entry=config_entry,
                        coordinator=coordinator_tuner,
                        device_name=device_name,
                        description=SensorEntityDescription(
                            key="",
                            name=device_name,
                            translation_key="tuner_status",
                        ),
                    ),
                    HDHomerunTunerSensor(
                        config_entry=config_entry,
                        coordinator=coordinator_tuner,
                        device_name=device_name,
                        description=SensorEntityDescription(
                            device_class=SensorDeviceClass.FREQUENCY,
                            key="Frequency",
                            name=f"{device_name} Frequency",
                            native_unit_of_measurement=UnitOfFrequency.HERTZ,
                            translation_key="tuner_frequency",
                        ),
                    ),
                    HDHomerunTunerSensor(
                        config_entry=config_entry,
                        coordinator=coordinator_tuner,
                        device_name=device_name,
                        description=SensorEntityDescription(
                            device_class=SensorDeviceClass.DATA_RATE,
                            key="NetworkRate",
                            name=f"{device_name} Network Rate",
                            native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
                            translation_key="tuner_network_rate",
                        ),
                    ),
                    HDHomerunTunerSensor(
                        config_entry=config_entry,
                        coordinator=coordinator_tuner,
                        device_name=device_name,
                        description=SensorEntityDescription(
                            key="SignalQualityPercent",
                            name=f"{device_name} Signal Quality",
                            native_unit_of_measurement=PERCENTAGE,
                            translation_key="tuner_signal_quality",
                        ),
                    ),
                    HDHomerunTunerSensor(
                        config_entry=config_entry,
                        coordinator=coordinator_tuner,
                        device_name=device_name,
                        description=SensorEntityDescription(
                            key="SignalStrengthPercent",
                            name=f"{device_name} Signal Strength",
                            native_unit_of_measurement=PERCENTAGE,
                            translation_key="tuner_signal_strength",
                        ),
                    ),
                    HDHomerunTunerSensor(
                        config_entry=config_entry,
                        coordinator=coordinator_tuner,
                        device_name=device_name,
                        description=SensorEntityDescription(
                            key="SymbolQualityPercent",
                            name=f"{device_name} Symbol Quality",
                            native_unit_of_measurement=PERCENTAGE,
                            translation_key="tuner_symbol_quality",
                        ),
                    ),
                    HDHomerunTunerSensor(
                        config_entry=config_entry,
                        coordinator=coordinator_tuner,
                        device_name=device_name,
                        description=SensorEntityDescription(
                            key="TargetIP",
                            name=f"{device_name} Target IP",
                            translation_key="tuner_target_ip",
                        ),
                    ),
                ]
            )
    # endregion

    # region #-- add conditional sensors --#
    if coordinator_general.data.discovery_method is DiscoverMode.HTTP:
        sensors.extend(
            [
                HDHomerunSensor(
                    additional_description=AdditionalSensorDescription(
                        extra_attributes=lambda d: (
                            {
                                "channels": [
                                    channel.get("GuideName", None)
                                    for channel in d.channels
                                    if channel.get("Enabled", None) == 0
                                ]
                            }
                        ),
                        state_value=lambda d: len(
                            [
                                channel
                                for channel in d
                                if channel.get("Enabled", None) == 0
                            ]
                        ),
                    ),
                    config_entry=config_entry,
                    coordinator=coordinator_general,
                    description=SensorEntityDescription(
                        key="channels",
                        name="Disabled Channels",
                        state_class=SensorStateClass.MEASUREMENT,
                        translation_key="disabled_channels",
                    ),
                ),
                HDHomerunSensor(
                    additional_description=AdditionalSensorDescription(
                        extra_attributes=lambda d: (
                            {
                                "channels": [
                                    channel.get("GuideName", None)
                                    for channel in d.channels
                                    if channel.get("Favorite", None) == 1
                                ]
                            }
                        ),
                        state_value=lambda d: len(
                            [
                                channel
                                for channel in d
                                if channel.get("Favorite", None) == 1
                            ]
                        ),
                    ),
                    config_entry=config_entry,
                    coordinator=coordinator_general,
                    description=SensorEntityDescription(
                        key="channels",
                        name="Favourite Channels",
                        state_class=SensorStateClass.MEASUREMENT,
                        translation_key="fav_channels",
                    ),
                ),
                HDHomerunSensor(
                    config_entry=config_entry,
                    coordinator=coordinator_general,
                    description=SensorEntityDescription(
                        device_class=SensorDeviceClass.TIMESTAMP,
                        key="lineup_fetched_at",
                        name="Lineup Updated",
                        translation_key="lineup_updated",
                    ),
                ),
                HDHomerunSensor(
                    additional_description=AdditionalSensorDescription(
                        # pylint: disable=unnecessary-lambda
                        state_value=lambda d: len(d),
                    ),
                    config_entry=config_entry,
                    coordinator=coordinator_general,
                    description=SensorEntityDescription(
                        key="channels",
                        name="Channel Count",
                        state_class=SensorStateClass.MEASUREMENT,
                        translation_key="channel_count",
                    ),
                ),
            ]
        )
    # endregion

    # region #-- add default sensors --#
    tuners_available = HDHomerunSensor(
        additional_description=AdditionalSensorDescription(
            state_value=lambda d: (
                len(d.tuner_status) - len(d.tuners_in_use) if d.tuner_status else None
            ),
        ),
        config_entry=config_entry,
        coordinator=coordinator_tuner,
        description=SensorEntityDescription(
            key="",
            name="Tuners Available",
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="tuners_available",
        ),
    )
    tuners_available._attr_entity_category = None  # useful for automations
    sensors.extend(
        [
            tuners_available,
            HDHomerunSensor(
                config_entry=config_entry,
                coordinator=coordinator_general,
                description=SensorEntityDescription(
                    key="tuner_count",
                    name="Tuner Count",
                    state_class=SensorStateClass.MEASUREMENT,
                    translation_key="tuner_count",
                ),
            )
        ]
    )
    # endregion

    async_add_entities(sensors)

    if sensors_to_remove:
        entity_cleanup(config_entry=config_entry, entities=sensors_to_remove, hass=hass)


# region #-- sensor classes --#
class HDHomerunSensor(HDHomerunEntity, SensorEntity):
    """Representation of an HDHomeRun sensor."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        description: SensorEntityDescription,
        additional_description: AdditionalSensorDescription | None = None,
    ) -> None:
        """Initialise."""
        self._additional_description: AdditionalSensorDescription | None = (
            additional_description
        )
        self.entity_domain = ENTITY_DOMAIN
        super().__init__(
            config_entry=config_entry,
            coordinator=coordinator,
            description=description,
        )

        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> StateType | date | datetime:
        """Get the value of the sensor."""
        if self.coordinator.data:
            if (
                self._additional_description is not None
                and self._additional_description.state_value
            ):
                if self.entity_description.key:
                    return self._additional_description.state_value(
                        getattr(
                            self.coordinator.data, self.entity_description.key, None
                        )
                    )
                return self._additional_description.state_value(self.coordinator.data)
            return getattr(self.coordinator.data, self.entity_description.key, None)

        return None


class HDHomerunTunerSensor(HDHomerunTunerEntity, SensorEntity):
    """Representation of an HDHomeRun tuner."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        description: SensorEntityDescription,
        device_name: str,
        additional_description: AdditionalSensorDescription | None = None,
    ) -> None:
        """Initialise."""
        self._additional_description: AdditionalSensorDescription | None = (
            additional_description
        )
        self.entity_domain = ENTITY_DOMAIN
        self._device_name: str = device_name

        super().__init__(
            config_entry=config_entry,
            coordinator=coordinator,
            description=description,
        )
        self._tuner: dict = self._get_tuner()
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def _get_tuner(self) -> dict[str, int | str]:
        """Get the tuner information from the coordinator."""
        tuner: dict[str, int | str] = {}
        for _tuner in self.coordinator.data.tuner_status:
            if _tuner.get("Resource", "").lower() == self._device_name.lower():
                tuner = _tuner
                break

        return tuner

    def _handle_coordinator_update(self) -> None:
        """Update the device information when the coordinator updates."""
        # Refresh the tuner before the base class writes state, or every tuner
        # sensor would report the previous poll.
        self._tuner = self._get_tuner()
        super()._handle_coordinator_update()

    @property
    def entity_picture(self) -> str | None:
        """Define the entity picture for the sensor."""
        if (
            self._additional_description is not None
            and self._additional_description.entity_picture
        ):
            return self._additional_description.entity_picture(
                self._tuner, self._config
            )

        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Define additional information for the sensor."""
        if (
            self._additional_description is not None
            and self._additional_description.extra_attributes
        ):
            return self._additional_description.extra_attributes(self._tuner)

        return None

    @property
    def native_value(self) -> StateType | date | datetime:
        """Get the value of the sensor."""
        if (
            self._additional_description is not None
            and self._additional_description.state_value
        ):
            return self._additional_description.state_value(self._tuner, self._config)

        if self.entity_description.key:
            return self._tuner.get(self.entity_description.key, None)

        return None


class HDHomerunTunerProgrammeSensor(HDHomerunTunerSensor):
    """The cached guide programme airing on a tuner's current channel."""

    def __init__(self, proxy: EPGProxy, **kwargs) -> None:
        """Initialise."""
        self._proxy = proxy
        super().__init__(**kwargs)
        self._attr_entity_category = None

    def _lookup(self) -> tuple[str | None, Any, Any]:
        """Match the tuned channel to the guide; return its current/next programmes."""
        number, name = self._tuner.get("VctNumber"), self._tuner.get("VctName")
        if not number and not name:
            return None, None, None
        if (channel_id := self._proxy.index.match(number, name)) is None:
            return None, None, None
        return channel_id, *self._proxy.index.programmes(
            channel_id, datetime.now(timezone.utc)
        )

    @property
    def native_value(self) -> str | None:
        """Return the title of the programme airing now."""
        _, current, _ = self._lookup()
        return current.title[:255] if current and current.title else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return programme details; keys are always present."""
        channel_id, current, upcoming = self._lookup()
        return {
            "channel_id": channel_id,
            "subtitle": current.subtitle if current else None,
            "episode": current.episode if current else None,
            "description": current.description if current else None,
            "start": current.start.isoformat() if current else None,
            "stop": current.stop.isoformat() if current else None,
            "next_title": upcoming.title if upcoming else None,
            "next_start": upcoming.start.isoformat() if upcoming else None,
        }


# endregion
