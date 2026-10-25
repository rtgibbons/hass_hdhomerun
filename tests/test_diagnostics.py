"""Diagnostics and discovery must not disclose receiver authentication."""

import copy
import json
import logging
import struct
from types import SimpleNamespace
import zlib

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import ExtendedJSONEncoder

from custom_components.hdhomerun.const import (
    CONF_DATA_COORDINATOR_GENERAL,
    CONF_DATA_COORDINATOR_TUNER_STATUS,
    DOMAIN,
)
from custom_components.hdhomerun.diagnostics import async_get_config_entry_diagnostics
from custom_components.hdhomerun.pyhdhr.const import DiscoverMode
from custom_components.hdhomerun.pyhdhr.device import HDHomeRunDevice
from custom_components.hdhomerun.pyhdhr.discover import _DiscoverProtocol


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [DiscoverMode.HTTP, DiscoverMode.UDP])
async def test_diagnostics_hide_named_and_encoded_credentials_without_mutating_device(
    tmp_path, mode
):
    hass = HomeAssistant(str(tmp_path))
    entry = SimpleNamespace(entry_id="receiver")
    device = HDHomeRunDevice("192.0.2.10", mode)
    secret = "synthetic-device-auth-ABC"
    device_id = "1234ABCD"
    device._raw_details = {"discover": {
        "DeviceAuth": secret, "DeviceID": device_id, "ModelNumber": "HDHR5-4DT",
    }}
    # Cover stale/legacy packets as well as fresh discovery. HA's JSON export
    # stringifies numeric keys, but diagnostics first receives integer tags.
    device._processed_datagram = {"header": 3, "data": {
        "raw": b"packet:" + secret.encode() + bytes.fromhex(device_id),
        43: secret.encode(), "43": {"repr": repr(secret.encode())},
        2: bytes.fromhex(device_id), "2": {"repr": repr(bytes.fromhex(device_id))},
    }}
    tuner = HDHomeRunDevice("192.0.2.10", mode)
    tuner._tuner_status = [{"Resource": "tuner0", "SignalQualityPercent": 87}]
    original_details = copy.deepcopy(device._raw_details)
    original_datagram = copy.deepcopy(device._processed_datagram)
    hass.data[DOMAIN] = {entry.entry_id: {
        CONF_DATA_COORDINATOR_GENERAL: SimpleNamespace(data=device),
        CONF_DATA_COORDINATOR_TUNER_STATUS: SimpleNamespace(data=tuner),
    }}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert secret not in repr(result)
    assert device_id not in repr(result)
    assert repr(bytes.fromhex(device_id)) not in repr(result)
    exported = json.dumps(result, cls=ExtendedJSONEncoder)
    assert secret not in exported
    assert device_id not in exported
    assert result["device"]["hw_model"] == "HDHR5-4DT"
    assert result["device"]["raw_details"]["discover"]["ModelNumber"] == "HDHR5-4DT"
    assert result["device"]["tuner_status"] == [
        {"Resource": "tuner0", "SignalQualityPercent": 87}
    ]
    assert device._raw_details == original_details
    assert device._processed_datagram == original_datagram


def test_udp_discovery_does_not_log_or_retain_authentication(caplog):
    secret = b"synthetic-device-auth-ABC"
    # Real discovery response: tuner type, device ID, auth string, tuner count.
    payload = (b"\x01\x04\x00\x00\x00\x01\x02\x04\x12\x34\xab\xcd"
               + b"\x2b" + bytes([len(secret)]) + secret + b"\x10\x01\x04")
    packet = b"\x00\x03" + struct.pack(">H", len(payload)) + payload
    packet += struct.pack("<L", zlib.crc32(packet))
    protocol = _DiscoverProtocol(None, "127.0.0.1")

    with caplog.at_level(logging.DEBUG):
        protocol.datagram_received(packet, ("192.0.2.10", 65001))

    assert secret.decode() not in caplog.text
    device, = protocol.discovered_devices
    assert secret.decode() not in repr(device._processed_datagram)
    assert device.get_from_datagram(2) == "1234ABCD"
    assert device.get_from_datagram(16) == 4
