"""Tests for tuner availability derived from tuner status."""

from custom_components.hdhomerun.pyhdhr.const import DiscoverMode
from custom_components.hdhomerun.pyhdhr.device import HDHomeRunDevice


def test_tuners_in_use():
    """Idle tuners report only their resource name, over HTTP and UDP alike."""
    device = HDHomeRunDevice("192.0.2.1", DiscoverMode.HTTP)
    assert device.tuners_in_use == []
    device._tuner_status = [
        {"Resource": "tuner0", "VctNumber": "7.1", "TargetIP": "192.0.2.9"},
        {"Resource": "tuner1"},
        {"Resource": "tuner2", "Frequency": 177000000},  # scanning
    ]
    assert device.tuners_in_use == ["tuner0", "tuner2"]
