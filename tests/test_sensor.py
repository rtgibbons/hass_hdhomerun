"""Tests for sensor state and attribute plumbing."""

from types import SimpleNamespace

from homeassistant.components.sensor import SensorEntityDescription

from custom_components.hdhomerun.sensor import HDHomerunTunerSensor

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
