"""Optional per-device SiliconDust XMLTV cache and capability URL."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import secrets
from datetime import datetime, timezone
from xml.etree.ElementTree import Element

import aiohttp
from aiohttp import web
from defusedxml import ElementTree
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_SOURCE = "https://api.hdhomerun.com/api/xmltv"
_MAX_XML = 20 * 1024 * 1024  # Limit the *decompressed* body, including gzip responses.
_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def inspect_xmltv(xml: bytes) -> dict:
    """Reject malformed, oversized or non-guide responses; summarize coverage."""
    if len(xml) > _MAX_XML or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("XMLTV exceeds limit or contains a DTD")
    root: Element = ElementTree.fromstring(xml)
    if root.tag != "tv":
        raise ValueError("XMLTV root is not tv")
    channels = root.findall("channel")
    programmes = root.findall("programme")
    ids = {channel.get("id") for channel in channels if channel.get("id")}
    if not ids or not programmes or len(ids) != len(channels):
        raise ValueError("XMLTV needs uniquely identified channels and programmes")
    dates = []
    for programme in programmes:
        if programme.get("channel") not in ids:
            raise ValueError("Programme refers to an unknown channel")
        try:
            start = datetime.strptime(programme.attrib["start"], "%Y%m%d%H%M%S %z")
            stop = datetime.strptime(programme.attrib["stop"], "%Y%m%d%H%M%S %z")
        except (KeyError, ValueError) as exc:
            raise ValueError("Invalid programme time") from exc
        if stop <= start:
            raise ValueError("Invalid programme duration")
        dates.append((start, stop))
    return {
        "channels": len(channels),
        "programmes": len(programmes),
        "coverage_start": min(start for start, _ in dates).isoformat(),
        "coverage_end": max(stop for _, stop in dates).isoformat(),
        "channel_names": sorted(
            {
                name.text.strip()
                for channel in channels
                for name in channel.findall("display-name")
                if name.text and name.text.strip()
            }
        ),
    }


class EPGProxy:
    """Own one entry's durable snapshot and refresh job."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, host: str, interval: int
    ) -> None:
        """Initialize a private, atomic entry-scoped cache."""
        self.hass = hass
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
        self.fetched_at: str | None = None
        self.summary: dict = {}
        self.error: str | None = None
        self.listeners: list = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    async def load(self) -> None:
        """Restore a validated cache and token, without trusting stored metadata."""
        stored = await self.store.async_load() or {}
        if not isinstance(stored, dict):
            stored = {}
        token = stored.get("token")
        self.token = (
            token
            if isinstance(token, str)
            and len(token) == 64
            and all(c in "0123456789abcdef" for c in token)
            else secrets.token_hex(32)
        )
        xml = stored.get("xml")
        if isinstance(xml, str):
            try:
                self.summary = await self.hass.async_add_executor_job(
                    inspect_xmltv, xml.encode()
                )
            except (ValueError, ElementTree.ParseError):
                _LOGGER.warning("Discarding invalid stored XMLTV cache")
            else:
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
    ) -> None:
        await self.store.async_save(
            {
                "token": token if token is not None else self.token,
                "xml": xml if xml is not None else self.xml,
                "fetched_at": fetched_at if fetched_at is not None else self.fetched_at,
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
                summary = await self.hass.async_add_executor_job(
                    inspect_xmltv, bytes(body)
                )
                xml = body.decode("utf-8")
                fetched_at = datetime.now(timezone.utc).isoformat()
                await self._save(xml=xml, fetched_at=fetched_at)
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
                _LOGGER.warning(
                    "XMLTV refresh failed (%s); keeping last good cache", self.error
                )
                self.notify()
                return False
            self.xml, self.fetched_at, self.summary, self.error = (
                xml,
                fetched_at,
                summary,
                None,
            )
            self.notify()
            return True

    async def rotate(self, tokens: dict[str, EPGProxy]) -> None:
        """Commit a new capability before revoking the old one."""
        async with self._lock:
            token = secrets.token_hex(32)
            await self._save(token=token)
            tokens.pop(self.token, None)
            self.token = token
            tokens[token] = self
            self.notify()

    def start(self) -> None:
        """Start jittered polling; the first attempt is soon, not during setup."""
        self._task = self.hass.async_create_background_task(
            self._run(), "HDHomeRun XMLTV refresh"
        )

    async def _run(self) -> None:
        try:
            await asyncio.sleep(random.uniform(0, 300))
            while True:
                await self.refresh()
                await asyncio.sleep(self.interval * 3600 * random.uniform(0.9, 1.1))
        except asyncio.CancelledError:
            return

    def stop(self) -> None:
        """Stop polling when the entry unloads."""
        if self._task:
            self._task.cancel()


class XMLTVView(HomeAssistantView):
    """Read-only capability endpoint; no Home Assistant bearer token required."""

    url = "/api/hdhomerun/xmltv/{token}"
    name = "api:hdhomerun:xmltv"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        """Serve only currently loaded, enabled entries with a good snapshot."""
        proxy = request.app[KEY_HASS].data[DOMAIN]["_epg_tokens"].get(token)
        if proxy is None:
            raise web.HTTPNotFound()
        if proxy.xml is None:
            raise web.HTTPServiceUnavailable(headers=_HEADERS)
        return web.Response(
            text=proxy.xml, content_type="application/xml", headers=_HEADERS
        )
