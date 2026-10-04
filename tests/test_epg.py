"""Tests for the optional XMLTV cache, validation and capability endpoint."""

import json
from types import SimpleNamespace

import pytest
from aiohttp import web
from homeassistant.components.http import KEY_HASS

from custom_components.hdhomerun import epg

GUIDE = (
    b'<tv><channel id="7"><display-name>7.1</display-name></channel>'
    b'<programme channel="7" start="20261004080000 -0500" '
    b'stop="20261004090000 -0500"><title>News</title></programme></tv>'
)


def test_xmltv_validation():
    """Reject wrong roots, broken references/times and DTDs."""
    summary = epg.inspect_xmltv(GUIDE)
    assert (summary["channels"], summary["programmes"]) == (1, 1)
    assert summary["coverage_start"] == "2026-10-04T08:00:00-05:00"
    assert summary["channel_names"] == ["7.1"]
    for invalid in (
        b"<html>Forbidden</html>",
        b"<tv><channel id='7'/></tv>",
        GUIDE.replace(b'channel="7" start', b'channel="8" start'),
        GUIDE.replace(b"20261004090000", b"20261004070000"),
        b'<!DOCTYPE tv [<!ENTITY x "oops">]>' + GUIDE,
    ):
        with pytest.raises(ValueError):
            epg.inspect_xmltv(invalid)


class Store:
    def __init__(self, data=None):
        self.data = data
        self.fail = False

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        if self.fail:
            raise OSError("disk full")
        self.data = data


class Response:
    def __init__(self, body):
        self.body = body
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def raise_for_status(self):
        pass

    async def read(self, _):
        return self.body

    async def iter_chunked(self, _):
        yield self.body


class Session:
    def __init__(self, xml):
        self.xml = xml
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if url.endswith("discover.json"):
            return Response(json.dumps({"DeviceAuth": "fresh-secret"}).encode())
        return Response(self.xml)


class Hass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


@pytest.mark.asyncio
async def test_refresh_failure_retains_snapshot_and_rotation_revokes(monkeypatch):
    session = Session(GUIDE)
    monkeypatch.setattr(epg, "async_get_clientsession", lambda _: session)
    monkeypatch.setattr(epg, "Store", lambda *args, **kwargs: Store())
    proxy = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await proxy.load()
    old_token = proxy.token
    await proxy.refresh()
    assert session.requests[0][0] == "http://192.0.2.1/discover.json"
    assert session.requests[1][1]["params"] == {"DeviceAuth": "fresh-secret"}
    assert all(kwargs["allow_redirects"] is False for _, kwargs in session.requests)
    assert session.requests[1][1]["headers"]["Accept-Encoding"] == "gzip"
    assert "fresh-secret" not in repr(proxy.store.data)
    assert proxy.xml == GUIDE.decode()
    session.xml = b"Forbidden"
    await proxy.refresh()
    assert proxy.xml == GUIDE.decode() and proxy.error == "ParseError"
    assert proxy.store.data["xml"] == GUIDE.decode()

    tokens = {old_token: proxy}
    await proxy.rotate(tokens)
    assert old_token not in tokens and tokens[proxy.token] is proxy
    request = SimpleNamespace(
        app={KEY_HASS: SimpleNamespace(data={"hdhomerun": {"_epg_tokens": tokens}})}
    )
    with pytest.raises(web.HTTPNotFound):
        await epg.XMLTVView().get(request, old_token)
    result = await epg.XMLTVView().get(request, proxy.token)
    assert result.text == GUIDE.decode()
    assert result.headers["Cache-Control"] == "no-store"

    latest = proxy.token
    proxy.store.fail = True
    with pytest.raises(OSError):
        await proxy.rotate(tokens)
    assert proxy.token == latest and latest in tokens


@pytest.mark.asyncio
async def test_oversize_and_restart_keep_good_cache(monkeypatch):
    """Do not replace a good snapshot with an oversized feed; restore it on restart."""
    session = Session(GUIDE)
    monkeypatch.setattr(epg, "async_get_clientsession", lambda _: session)
    stored = Store()
    monkeypatch.setattr(epg, "Store", lambda *args, **kwargs: stored)
    proxy = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await proxy.load()
    assert await proxy.refresh()
    monkeypatch.setattr(epg, "_MAX_XML", len(GUIDE) + 1)
    session.xml = GUIDE + b"extra"
    assert not await proxy.refresh()
    assert proxy.xml == GUIDE.decode()
    restored = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await restored.load()
    assert restored.token == proxy.token
    assert restored.xml == GUIDE.decode()
    assert restored.fetched_at == proxy.fetched_at
