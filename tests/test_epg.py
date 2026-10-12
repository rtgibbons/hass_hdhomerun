"""Tests for the optional XMLTV cache, validation and capability endpoint."""

import gzip
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from homeassistant.components.http import KEY_HASS
from defusedxml import ElementTree
from yarl import URL

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
    for invalid in (
        b"<html>Forbidden</html>",
        b"<tv><channel id='7'/></tv>",
        GUIDE.replace(b'channel="7" start', b'channel="8" start'),
        GUIDE.replace(b"20261004090000", b"20261004070000"),
        b'<!DOCTYPE tv [<!ENTITY x "oops">]>' + GUIDE,
    ):
        with pytest.raises(ValueError):
            epg.inspect_xmltv(invalid)


def test_incremental_validation_handles_order_and_size_boundary(monkeypatch):
    """Channel references may precede definitions; the cap is inclusive."""
    channel = b'<channel id="7"><display-name>7.1</display-name></channel>'
    programme = GUIDE.split(b"</channel>", 1)[1].removesuffix(b"</tv>")
    reordered = b"<tv>" + programme + channel + b"</tv>"
    assert epg.inspect_xmltv(reordered)["programmes"] == 1
    monkeypatch.setattr(epg, "_MAX_XML", len(reordered))
    assert epg.inspect_xmltv(reordered)["channels"] == 1
    monkeypatch.setattr(epg, "_MAX_XML", len(reordered) - 1)
    with pytest.raises(ValueError):
        epg.inspect_xmltv(reordered)


def test_14_day_feed_larger_than_old_limit():
    """A plausible 14-day guide must pass the new bounded parser."""
    first = datetime(2026, 10, 5, tzinfo=timezone.utc)
    description = b"x" * 1_600_000
    programmes = []
    for day in range(14):
        start = first + timedelta(days=day)
        stop = start + timedelta(days=1)
        programmes.append(
            b'<programme channel="7" start="'
            + start.strftime("%Y%m%d%H%M%S +0000").encode()
            + b'" stop="'
            + stop.strftime("%Y%m%d%H%M%S +0000").encode()
            + b'"><desc>'
            + description
            + b"</desc></programme>"
        )
    guide = b'<tv><channel id="7"/>' + b"".join(programmes) + b"</tv>"
    assert 20 * 1024 * 1024 < len(guide) < epg._MAX_XML
    summary = epg.inspect_xmltv(guide)
    assert summary["programmes"] == 14
    assert summary["coverage_end"] == "2026-10-19T00:00:00+00:00"


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
    indexed = proxy.index
    await proxy.refresh()
    assert proxy.xml == GUIDE.decode() and proxy.error == "ParseError"
    assert gzip.decompress(proxy.xml_gzip) == GUIDE
    assert proxy.index is not indexed  # reindexed from the cache
    assert proxy.store.data["xml"] == GUIDE.decode()
    session.xml = GUIDE.replace(b"News", b"Weather")
    proxy.store.fail = True
    assert not await proxy.refresh()
    assert proxy.xml == GUIDE.decode()
    assert gzip.decompress(proxy.xml_gzip) == GUIDE
    proxy.store.fail = False

    tokens = {old_token: proxy}
    await proxy.rotate(tokens)
    assert old_token not in tokens and tokens[proxy.token] is proxy
    request = SimpleNamespace(
        app={KEY_HASS: SimpleNamespace(data={"hdhomerun": {"_epg_tokens": tokens}})},
        path=f"/api/hdhomerun/xmltv/{proxy.token}",
        headers={},
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
    assert gzip.decompress(restored.xml_gzip) == GUIDE


@pytest.mark.asyncio
async def test_short_tokens_and_compressed_http_formats(monkeypatch):
    """Serve identical guides with negotiated gzip or explicit gzip-file URLs."""
    stored = Store({"token": "a" * 64, "xml": GUIDE.decode()})
    monkeypatch.setattr(epg, "Store", lambda *args, **kwargs: stored)
    proxy = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await proxy.load()
    assert len(proxy.token) == 22
    assert stored.data["token"] == proxy.token
    restored = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await restored.load()
    assert restored.token == proxy.token
    tokens = {proxy.token: proxy}
    app = web.Application()
    app[KEY_HASS] = SimpleNamespace(data={"hdhomerun": {"_epg_tokens": tokens}})
    view = epg.XMLTVView()

    async def serve(request):
        return await view.get(request, request.match_info["token"])

    for route in [view.url, *view.extra_urls]:
        app.router.add_get(route, serve)
    async with TestClient(TestServer(app), auto_decompress=False) as client:
        path = f"/api/hdhomerun/xmltv/{proxy.token}"
        for encoding, compressed in (
            ("identity", False),
            ("gzip", True),
            ("br, gzip;q=0.5", True),
            ("gzip;q=0.5, identity;q=1", False),
            ("*;q=1, gzip;q=0", False),
            ("*;q=0.5", True),
            ("gzip;q=invalid", False),
        ):
            response = await client.get(path, headers={"Accept-Encoding": encoding})
            assert response.status == 200
            body = await response.read()
            assert (gzip.decompress(body) if compressed else body) == GUIDE
            assert response.headers.get("Content-Encoding") == ("gzip" if compressed else None)
            assert response.headers["Vary"] == "Accept-Encoding"
        for encoding in ("gzip;q=0, identity;q=0", "*;q=0"):
            response = await client.get(path, headers={"Accept-Encoding": encoding})
            assert response.status == 406
        response = await client.get(path + ".xml.gz")
        assert response.status == 200
        assert response.content_type == "application/gzip"
        assert "Content-Encoding" not in response.headers
        assert gzip.decompress(await response.read()) == GUIDE
        assert (await client.get("/api/hdhomerun/xmltv/" + "a" * 64)).status == 404
        await proxy.rotate(tokens)
        assert len(proxy.token) == 22
        assert (await client.get(path)).status == 404
        assert (await client.get(path + ".xml.gz")).status == 404
        proxy.xml = None
        assert (await client.get(f"/api/hdhomerun/xmltv/{proxy.token}.xml.gz")).status == 503


def test_guide_index_matches_lineup_numbers_then_names():
    """Prefer the virtual channel number; fall back to an unambiguous name."""
    guide = (
        b'<tv><channel id="US1.hdhomerun.com"><display-name>KOMO</display-name>'
        b"<lcn>4.1</lcn><icon src=\"http://logo/komo.png\"/></channel>"
        b'<channel id="US2.hdhomerun.com"><display-name>KOMO</display-name>'
        b"<lcn>4.2</lcn></channel>"
        b'<channel id="US3.hdhomerun.com"><display-name>Bounce</display-name></channel>'
        b'<programme channel="US1.hdhomerun.com" start="20261004080000 +0000" '
        b'stop="20261004090000 +0000"><title>News</title></programme></tv>'
    )
    _, index = epg.parse_xmltv(guide)
    assert index.match("4.1", "KOMO") == "US1.hdhomerun.com"
    assert index.match("4.2", "Other") == "US2.hdhomerun.com"
    assert index.match("9.9", "KOMO") is None  # ambiguous name
    assert index.match("9.9", " bounce ") == "US3.hdhomerun.com"
    assert index.match(None, None) is None

    lineup = [
        {"GuideNumber": "4.1", "GuideName": "KOMO", "URL": "http://tuner:5004/auto/v4.1"},
        {"GuideNumber": "9.9", "GuideName": 'Odd "name"\n', "URL": "http://tuner:5004/auto/v9.9"},
        {"GuideNumber": "5.1", "GuideName": "Locked", "DRM": 1, "URL": "http://x"},
        {"GuideNumber": "6.1", "GuideName": "Hidden", "Enabled": 0, "URL": "http://x"},
        {"GuideNumber": "7.1", "GuideName": "No URL"},
    ]
    playlist = epg.build_m3u(lineup, index, "http://ha/api/hdhomerun/xmltv/t")
    assert playlist.splitlines() == [
        '#EXTM3U url-tvg="http://ha/api/hdhomerun/xmltv/t" '
        'x-tvg-url="http://ha/api/hdhomerun/xmltv/t"',
        '#EXTINF:-1 channel-id="4.1" channel-number="4.1" tvg-chno="4.1" '
        'tvg-name="KOMO" tvg-id="US1.hdhomerun.com" '
        'tvg-logo="http://logo/komo.png",KOMO',
        "http://tuner:5004/auto/v4.1",
        '#EXTINF:-1 channel-id="9.9" channel-number="9.9" tvg-chno="9.9" '
        "tvg-name=\"Odd 'name'\",Odd 'name'",
        "http://tuner:5004/auto/v9.9",
    ]


@pytest.mark.asyncio
async def test_m3u_view_uses_capability_token(monkeypatch):
    """Serve the playlist only for live tokens and only once a lineup exists."""
    monkeypatch.setattr(epg, "Store", lambda *args, **kwargs: Store())
    lineup = []
    proxy = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6, lineup=lambda: lineup)
    await proxy.load()
    request = SimpleNamespace(
        app={KEY_HASS: SimpleNamespace(data={"hdhomerun": {"_epg_tokens": {proxy.token: proxy}}})},
        url=URL("http://ha:8123/api/hdhomerun/m3u/" + proxy.token + "?x=1"),
    )
    with pytest.raises(web.HTTPNotFound):
        await epg.M3UView().get(request, "wrong")
    with pytest.raises(web.HTTPServiceUnavailable):
        await epg.M3UView().get(request, proxy.token)
    lineup.append({"GuideNumber": "7.1", "GuideName": "Seven", "URL": "http://tuner/v7.1"})
    result = await epg.M3UView().get(request, proxy.token)
    assert result.content_type == "audio/x-mpegurl"
    assert result.headers["Cache-Control"] == "no-store"
    assert f'url-tvg="http://ha:8123/api/hdhomerun/xmltv/{proxy.token}"' in result.text
    assert "http://tuner/v7.1" in result.text


@pytest.mark.asyncio
async def test_status_sensor_urls_and_lineup_matches(monkeypatch):
    """The status sensor exposes every capability URL and lineup match counts."""
    from custom_components.hdhomerun.const import CONF_DATA_COORDINATOR_GENERAL
    from custom_components.hdhomerun.sensor import EPGStatus

    monkeypatch.setattr(epg, "Store", lambda *args, **kwargs: Store())
    proxy = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await proxy.load()
    proxy.summary, proxy.index = epg.parse_xmltv(GUIDE)
    lineup = [{"GuideNumber": "7.1", "GuideName": "Seven"}, {"GuideNumber": "8.1"}]
    sensor = EPGStatus(SimpleNamespace(entry_id="entry", unique_id="1234ABCD"), proxy)
    sensor.hass = SimpleNamespace(
        config=SimpleNamespace(external_url="https://ha.example/", internal_url=None),
        data={"hdhomerun": {"entry": {CONF_DATA_COORDINATOR_GENERAL: SimpleNamespace(
            data=SimpleNamespace(channels=lineup))}}},
    )
    attrs = sensor.extra_state_attributes
    base = "https://ha.example/api/hdhomerun"
    assert attrs["url"] == f"{base}/xmltv/{proxy.token}"
    assert attrs["gzip_url"] == f"{base}/xmltv/{proxy.token}.xml.gz"
    assert attrs["m3u_url"] == f"{base}/m3u/{proxy.token}"
    assert (attrs["lineup_channels"], attrs["lineup_name_matches"]) == (2, 1)
    assert attrs["unmatched_lineup_examples"] == ["8.1 "]


def test_schedule_window_and_now_playing_lookup():
    """Index only the upcoming window; find the current and next programme."""
    guide = (
        b'<tv><channel id="7"><lcn>7.1</lcn></channel>'
        b'<programme channel="7" start="20261004060000 +0000" stop="20261004080000 +0000">'
        b"<title>Old</title></programme>"
        b'<programme channel="7" start="20261004090000 +0000" stop="20261004100000 +0000">'
        b"<title>Later</title></programme>"
        b'<programme channel="7" start="20261004080000 +0000" stop="20261004090000 +0000">'
        b'<title>News</title><sub-title>Morning</sub-title><desc>'
        + b"d" * 600
        + b'</desc><episode-num system="xmltv_ns">1.4.0/1</episode-num></programme>'
        b'<programme channel="7" start="20261007080000 +0000" stop="20261007090000 +0000">'
        b"<title>Too far</title></programme></tv>"
    )
    now = datetime(2026, 10, 4, 8, 30, tzinfo=timezone.utc)
    summary, index = epg.parse_xmltv(guide, now)
    assert summary["programmes"] == 4
    assert [p.title for p in index.schedule["7"]] == ["News", "Later"]
    current, upcoming = index.programmes("7", now)
    assert (current.title, current.subtitle, current.episode) == ("News", "Morning", "S02E05")
    assert len(current.description) == 500
    assert upcoming.title == "Later"
    gap, upcoming = index.programmes("7", datetime(2026, 10, 4, 10, tzinfo=timezone.utc))
    assert gap is None and upcoming is None
    assert index.programmes("missing", now) == (None, None)


def test_episode_numbers():
    """Prefer onscreen numbering and tolerate partial xmltv_ns values."""
    def episode(numbers):
        return epg._episode(ElementTree.fromstring(f"<programme>{numbers}</programme>"))

    assert episode('<episode-num system="onscreen">S3 E7</episode-num>'
                   '<episode-num system="xmltv_ns">0.0.</episode-num>') == "S3 E7"
    assert episode('<episode-num system="xmltv_ns">.11/20.</episode-num>') == "E12"
    assert episode('<episode-num system="dd_progid">EP1</episode-num>') is None
