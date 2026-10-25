"""Optional per-device SiliconDust XMLTV cache and capability URL."""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import random
import secrets
from bisect import bisect_right
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from functools import partial
from io import BytesIO
from typing import NamedTuple
from xml.etree.ElementTree import Element

import aiohttp
from aiohttp import web
from defusedxml import ElementTree
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_SOURCE = "https://api.hdhomerun.com/api/xmltv"
_MAX_XML = 48 * 1024 * 1024  # Limit the *decompressed* body, including gzip responses.
# Programmes kept in memory for now-playing lookups; rebuilt on each refresh
# attempt, which always runs well within this window.
_SCHEDULE_WINDOW = timedelta(hours=48)
_MAX_DESCRIPTION = 500
_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def _key(value: object) -> str:
    """Normalize a channel number or name for matching."""
    return " ".join(str(value).split()).casefold()


class Programme(NamedTuple):
    """A guide entry kept for now-playing lookups."""

    start: datetime
    stop: datetime
    title: str | None
    subtitle: str | None
    episode: str | None
    description: str | None


def _text(element: Element, tag: str) -> str | None:
    """Return the stripped text of the first child with the given tag."""
    child = element.find(tag)
    return (child.text.strip() or None) if child is not None and child.text else None


def _episode(element: Element) -> str | None:
    """Prefer the on-screen episode number; otherwise convert xmltv_ns."""
    numbers = {
        number.get("system"): (number.text or "").strip()
        for number in element.findall("episode-num")
    }
    if numbers.get("onscreen"):
        return numbers["onscreen"]
    parts = [part.split("/")[0].strip() for part in numbers.get("xmltv_ns", "").split(".")]
    if len(parts) >= 2 and parts[1].isdigit():
        episode = f"E{int(parts[1]) + 1:02d}"
        return f"S{int(parts[0]) + 1:02d}{episode}" if parts[0].isdigit() else episode
    return None


class GuideIndex:
    """Match HDHomeRun lineup channels to XMLTV channel IDs and programmes."""

    def __init__(self) -> None:
        """Start with no guide channels."""
        self._keys: dict[str, set[str]] = {}
        self.icons: dict[str, str] = {}
        self.schedule: dict[str, list[Programme]] = {}

    def programmes(
        self, channel_id: str, when: datetime
    ) -> tuple[Programme | None, Programme | None]:
        """Return the programme airing at a time and the one after it."""
        schedule = self.schedule.get(channel_id, [])
        position = bisect_right(schedule, when, key=lambda programme: programme.start)
        current = schedule[position - 1] if position else None
        if current is not None and current.stop <= when:
            current = None
        return current, schedule[position] if position < len(schedule) else None

    def add_channel(self, channel_id: str, keys: list[str], icon: str | None) -> None:
        """Index a channel by its virtual channel number and display names."""
        for key in keys:
            self._keys.setdefault(_key(key), set()).add(channel_id)
        if icon:
            self.icons[channel_id] = icon

    def match(self, number: object, name: object) -> str | None:
        """Return the only XMLTV ID matching a lineup number and/or name."""
        by_number = self._keys.get(_key(number), set()) if number else set()
        by_name = self._keys.get(_key(name), set()) if name else set()
        combined = self._keys.get(_key(f"{number} {name}"), set())
        for candidates in (by_number & by_name, by_number, by_name, combined):
            if len(candidates) == 1:
                return next(iter(candidates))
        return None


def parse_xmltv(xml: bytes, now: datetime | None = None) -> tuple[dict, GuideIndex]:
    """Reject malformed, oversized or non-guide responses; summarize and index.

    Only programmes airing between now and the schedule window are indexed.
    """
    now = now or datetime.now(timezone.utc)
    if len(xml) > _MAX_XML or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("XMLTV exceeds limit or contains a DTD")
    root: Element | None = None
    depth = 0
    ids: set[str] = set()
    used_ids: set[str] = set()
    index = GuideIndex()
    programmes = 0
    first_start: datetime | None = None
    last_stop: datetime | None = None
    for event, element in ElementTree.iterparse(BytesIO(xml), events=("start", "end")):
        if event == "start":
            depth += 1
            if root is None:
                if element.tag != "tv":
                    raise ValueError("XMLTV root is not tv")
                root = element
            continue
        if depth == 2:
            if element.tag == "channel":
                channel_id = element.get("id")
                if not channel_id or channel_id in ids:
                    raise ValueError("XMLTV needs uniquely identified channels")
                ids.add(channel_id)
                icon = element.find("icon")
                index.add_channel(
                    channel_id,
                    [
                        child.text
                        for child in element
                        if child.tag in ("lcn", "display-name")
                        and child.text
                        and child.text.strip()
                    ],
                    icon.get("src") if icon is not None else None,
                )
            elif element.tag == "programme":
                used_ids.add(element.get("channel", ""))
                try:
                    start = datetime.strptime(
                        element.attrib["start"], "%Y%m%d%H%M%S %z"
                    )
                    stop = datetime.strptime(element.attrib["stop"], "%Y%m%d%H%M%S %z")
                except (KeyError, ValueError) as exc:
                    raise ValueError("Invalid programme time") from exc
                if stop <= start:
                    raise ValueError("Invalid programme duration")
                first_start = min(first_start, start) if first_start else start
                last_stop = max(last_stop, stop) if last_stop else stop
                programmes += 1
                if stop > now and start < now + _SCHEDULE_WINDOW:
                    description = _text(element, "desc")
                    index.schedule.setdefault(element.get("channel", ""), []).append(
                        Programme(
                            start,
                            stop,
                            _text(element, "title"),
                            _text(element, "sub-title"),
                            _episode(element),
                            description[:_MAX_DESCRIPTION] if description else None,
                        )
                    )
            root.clear()
        depth -= 1
    if not ids or not programmes or not used_ids <= ids:
        raise ValueError("XMLTV needs channels and programmes with valid references")
    for schedule in index.schedule.values():
        schedule.sort(key=lambda programme: programme.start)
    return {
        "channels": len(ids),
        "programmes": programmes,
        "coverage_start": first_start.isoformat(),
        "coverage_end": last_stop.isoformat(),
    }, index


def inspect_xmltv(xml: bytes) -> dict:
    """Validate a guide and return its coverage summary."""
    return parse_xmltv(xml)[0]


def _m3u_value(value: object) -> str:
    """Keep a value on one line and inside a quoted M3U attribute."""
    return " ".join(str(value).split()).replace('"', "'")


def build_m3u(lineup: list[dict], index: GuideIndex, xmltv_url: str) -> str:
    """Build a playlist whose tvg-id values match the cached XMLTV channel IDs."""
    lines = [f'#EXTM3U url-tvg="{xmltv_url}" x-tvg-url="{xmltv_url}"']
    for channel in lineup:
        url = channel.get("URL")
        if (
            not url
            or channel.get("DRM") == 1
            or channel.get("Enabled") == 0
            or "hidden" in str(channel.get("Tags", "")).split(",")
        ):
            continue
        number = _m3u_value(channel.get("GuideNumber", ""))
        name = _m3u_value(channel.get("GuideName", "")) or number
        attrs = [
            f'channel-id="{number}"',
            f'channel-number="{number}"',
            f'tvg-chno="{number}"',
            f'tvg-name="{name}"',
        ]
        if channel_id := index.match(channel.get("GuideNumber"), channel.get("GuideName")):
            attrs.append(f'tvg-id="{_m3u_value(channel_id)}"')
            if icon := index.icons.get(channel_id):
                attrs.append(f'tvg-logo="{_m3u_value(icon)}"')
        lines.append(f"#EXTINF:-1 {' '.join(attrs)},{name}")
        lines.append(_m3u_value(url))
    return "\n".join(lines) + "\n"


class EPGProxy:
    """Own one entry's durable snapshot and refresh job."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        host: str,
        interval: int,
        lineup: Callable[[], list[dict]] = list,
    ) -> None:
        """Initialize a private, atomic entry-scoped cache."""
        self.hass = hass
        self.lineup = lineup
        self.host = host
        self.interval = interval
        self.store = Store(
            hass,
            1,
            f"{DOMAIN}/epg_{entry_id}",
            private=True,
            atomic_writes=True,
            serialize_in_event_loop=False,
        )
        self.token = ""
        self.xml: str | None = None
        self.xml_gzip: bytes | None = None
        self.fetched_at: str | None = None
        self.summary: dict = {}
        self.index = GuideIndex()
        self.error: str | None = None
        self.consecutive_failures = 0
        self.last_failure: str | None = None
        self.listeners: list = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    async def load(self) -> None:
        """Restore a validated cache and token, without trusting stored metadata."""
        stored = await self.store.async_load() or {}
        if not isinstance(stored, dict):
            stored = {}
        failures = stored.get("consecutive_failures", 0)
        if type(failures) is int and failures >= 0:
            self.consecutive_failures = failures
        last_failure = stored.get("last_failure")
        if isinstance(last_failure, str):
            try:
                parsed_failure = datetime.fromisoformat(last_failure)
            except ValueError:
                pass
            else:
                if parsed_failure.tzinfo is not None:
                    self.last_failure = last_failure
        token = stored.get("token")
        self.token = (
            token
            if isinstance(token, str)
            and len(token) == 22
            and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in token)
            else secrets.token_urlsafe(16)
        )
        xml = stored.get("xml")
        if isinstance(xml, str):
            try:
                self.summary, self.index = await self.hass.async_add_executor_job(
                    parse_xmltv, xml.encode()
                )
            except (ValueError, ElementTree.ParseError):
                _LOGGER.warning("Discarding invalid stored XMLTV cache")
            else:
                self.xml_gzip = await self.hass.async_add_executor_job(
                    partial(gzip.compress, xml.encode(), compresslevel=6, mtime=0)
                )
                self.xml = xml
                fetched_at = stored.get("fetched_at")
                if isinstance(fetched_at, str):
                    try:
                        parsed = datetime.fromisoformat(fetched_at)
                    except ValueError:
                        pass
                    else:
                        if parsed.tzinfo is not None:
                            self.fetched_at = fetched_at
        if self.token != token:
            await self._save()

    async def _save(
        self,
        *,
        token: str | None = None,
        xml: str | None = None,
        fetched_at: str | None = None,
        consecutive_failures: int | None = None,
    ) -> None:
        await self.store.async_save(
            {
                "token": token if token is not None else self.token,
                "xml": xml if xml is not None else self.xml,
                "fetched_at": fetched_at if fetched_at is not None else self.fetched_at,
                "consecutive_failures": consecutive_failures if consecutive_failures is not None else self.consecutive_failures,
                "last_failure": self.last_failure,
            }
        )

    @callback
    def notify(self) -> None:
        """Update status entity after a fetch or rotation."""
        for listener in self.listeners:
            listener()

    async def refresh(self) -> bool:
        """Fetch with fresh local DeviceAuth, then replace the snapshot atomically."""
        async with self._lock:
            session = async_get_clientsession(self.hass)
            try:
                timeout = aiohttp.ClientTimeout(total=120)
                async with session.get(
                    f"http://{self.host}/discover.json",
                    timeout=timeout,
                    allow_redirects=False,
                    max_line_size=8190,
                ) as response:
                    response.raise_for_status()
                    discovery = await response.content.read(65537)
                    if len(discovery) > 65536:
                        raise ValueError("Discovery response exceeds size limit")
                    document = json.loads(discovery)
                    if not isinstance(document, dict):
                        raise TypeError("Invalid discovery response")
                    auth = document.get("DeviceAuth")
                if not isinstance(auth, str) or not auth or len(auth) > 512:
                    raise ValueError("DeviceAuth unavailable")
                async with session.get(
                    _SOURCE,
                    params={"DeviceAuth": auth},
                    headers={"Accept-Encoding": "gzip"},
                    timeout=timeout,
                    allow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        body.extend(chunk)
                        if len(body) > _MAX_XML:
                            raise ValueError("XMLTV exceeds size limit")
                summary, index = await self.hass.async_add_executor_job(
                    parse_xmltv, bytes(body)
                )
                xml = body.decode("utf-8")
                compressed = await self.hass.async_add_executor_job(
                    partial(gzip.compress, bytes(body), compresslevel=6, mtime=0)
                )
                fetched_at = datetime.now(timezone.utc).isoformat()
                await self._save(xml=xml, fetched_at=fetched_at, consecutive_failures=0)
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                TypeError,
                ValueError,
                UnicodeError,
                ElementTree.ParseError,
                OSError,
            ) as exc:
                # Never log exception text: aiohttp errors can include the DeviceAuth URL.
                self.error = (
                    f"HTTP {exc.status}"
                    if isinstance(exc, aiohttp.ClientResponseError)
                    else type(exc).__name__
                )
                self.consecutive_failures += 1
                self.last_failure = datetime.now(timezone.utc).isoformat()
                _LOGGER.warning(
                    "XMLTV refresh failed (%s); keeping last good cache", self.error
                )
                try:
                    await self._save()
                except OSError:
                    _LOGGER.warning("Could not persist XMLTV failure history")
                if self.xml is not None:
                    # Move the now-playing window forward while offline.
                    _, self.index = await self.hass.async_add_executor_job(
                        parse_xmltv, self.xml.encode()
                    )
                self.notify()
                return False
            (
                self.xml,
                self.xml_gzip,
                self.fetched_at,
                self.summary,
                self.index,
                self.error,
            ) = (
                xml,
                compressed,
                fetched_at,
                summary,
                index,
                None,
            )
            self.consecutive_failures = 0
            self.notify()
            return True

    async def rotate(self, tokens: dict[str, EPGProxy]) -> None:
        """Commit a new capability before revoking the old one."""
        async with self._lock:
            token = secrets.token_urlsafe(16)
            await self._save(token=token)
            tokens.pop(self.token, None)
            self.token = token
            tokens[token] = self
            self.notify()

    def start(self, refresh: Callable[[], Awaitable[object]] | None = None) -> None:
        """Start jittered polling; the first attempt is soon, not during setup."""
        self._task = self.hass.async_create_background_task(
            self._run(refresh or self.refresh), "HDHomeRun XMLTV refresh"
        )

    async def _run(self, refresh: Callable[[], Awaitable[object]]) -> None:
        try:
            await asyncio.sleep(random.uniform(0, 300))
            while True:
                try:
                    await refresh()
                except HomeAssistantError as exc:
                    # A failed button action must not stop subsequent refreshes.
                    _LOGGER.warning("Scheduled XMLTV refresh failed: %s", exc)
                await asyncio.sleep(self.interval * 3600 * random.uniform(0.9, 1.1))
        except asyncio.CancelledError:
            return

    def stop(self) -> None:
        """Stop polling when the entry unloads."""
        if self._task:
            self._task.cancel()


class XMLTVView(HomeAssistantView):
    """Read-only capability endpoint; no Home Assistant bearer token required."""

    url = "/api/hdhomerun/xmltv/{token:[A-Za-z0-9_-]{22}}"
    extra_urls = ["/api/hdhomerun/xmltv/{token:[A-Za-z0-9_-]{22}}.xml.gz"]
    name = "api:hdhomerun:xmltv"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        """Serve only currently loaded, enabled entries with a good snapshot."""
        proxy = request.app[KEY_HASS].data[DOMAIN]["_epg_tokens"].get(token)
        if proxy is None:
            raise web.HTTPNotFound()
        if proxy.xml is None:
            raise web.HTTPServiceUnavailable(headers=_HEADERS)
        if request.path.endswith(".xml.gz"):
            return web.Response(
                body=proxy.xml_gzip, content_type="application/gzip", headers=_HEADERS
            )
        headers = {**_HEADERS, "Vary": "Accept-Encoding"}
        encodings = {}
        for item in request.headers.get("Accept-Encoding", "").lower().split(","):
            encoding, *parameters = item.strip().split(";")
            quality = 1.0
            for parameter in parameters:
                if parameter.strip().startswith("q="):
                    try:
                        quality = float(parameter.strip()[2:])
                    except ValueError:
                        quality = 0.0
            encodings[encoding] = quality if 0 <= quality <= 1 else 0.0
        gzip_quality = encodings.get("gzip", encodings.get("*", 0))
        identity_quality = encodings.get(
            "identity", 0 if encodings.get("*") == 0 else 1
        )
        if gzip_quality > 0 and (
            "identity" not in encodings or gzip_quality >= identity_quality
        ):
            headers["Content-Encoding"] = "gzip"
            return web.Response(
                body=proxy.xml_gzip, content_type="application/xml", headers=headers
            )
        if identity_quality == 0:
            raise web.HTTPNotAcceptable(headers=headers)
        return web.Response(
            text=proxy.xml, content_type="application/xml", headers=headers
        )


class M3UView(HomeAssistantView):
    """Playlist for the same capability token, with tvg-id matched to the XMLTV."""

    url = "/api/hdhomerun/m3u/{token:[A-Za-z0-9_-]{22}}"
    name = "api:hdhomerun:m3u"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        """Serve playable lineup channels for currently loaded, enabled entries."""
        proxy = request.app[KEY_HASS].data[DOMAIN]["_epg_tokens"].get(token)
        if proxy is None:
            raise web.HTTPNotFound()
        lineup = proxy.lineup()
        if not lineup:
            raise web.HTTPServiceUnavailable(headers=_HEADERS)
        xmltv_url = str(
            request.url.with_path(f"/api/hdhomerun/xmltv/{token}").with_query(None)
        )
        return web.Response(
            text=build_m3u(lineup, proxy.index, xmltv_url),
            content_type="audio/x-mpegurl",
            headers=_HEADERS,
        )
