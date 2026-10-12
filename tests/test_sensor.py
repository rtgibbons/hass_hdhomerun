"""Tests for sensor state and attribute plumbing."""

from types import SimpleNamespace

from homeassistant.components.sensor import SensorEntityDescription

from custom_components.hdhomerun.sensor import (
    AdditionalSensorDescription,
    HDHomerunSensor,
    HDHomerunTunerSensor,
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
