"""Exercise the bundled frontend using HA's static-file server."""

from aiohttp.test_utils import TestClient, TestServer
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, UrlManager
from homeassistant.components.http import HomeAssistantHTTP, KEY_ALLOW_CONFIGURED_CORS
from homeassistant.core import HomeAssistant
import pytest

from custom_components.hdhomerun import dashboard
from custom_components.hdhomerun.dashboard import async_setup_frontend


@pytest.mark.asyncio
async def test_bundled_dashboard_is_served_without_creating_user_dashboards(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    hass.config.components.add("frontend")
    hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(lambda *_: None, [])
    hass.http = HomeAssistantHTTP(hass, None, None, None, None, 8123, [], "modern")
    # No authentication middleware is needed to exercise public static assets.
    hass.http.app[KEY_ALLOW_CONFIGURED_CORS] = lambda resource: None
    await async_setup_frontend(hass)
    urls = hass.data[DATA_EXTRA_MODULE_URL].urls
    assert len(urls) == 1
    url = next(iter(urls))
    assert url.startswith("/hdhomerun/frontend/")
    assert url.endswith("/strategy.js")
    async with TestClient(TestServer(hass.http.app)) as client:
        for filename in ("strategy.js", "cards.js", "localize.js"):
            response = await client.get(url.rsplit("/", 1)[0] + "/" + filename)
            assert response.status == 200
            assert "javascript" in response.headers["Content-Type"]
            assert len(await response.text()) > 100
        response = await client.get(url.rsplit("/", 1)[0] + "/manifest.json")
        assert response.status == 404
    assert not (tmp_path / ".storage" / "lovelace_dashboards").exists()


@pytest.mark.asyncio
async def test_headless_setup_has_no_frontend_side_effects(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    await async_setup_frontend(hass)
    assert DATA_EXTRA_MODULE_URL not in hass.data


@pytest.mark.asyncio
async def test_card_update_changes_module_tree_url(tmp_path, monkeypatch):
    """A changed imported card must bypass the old browser cache too."""
    assets = tmp_path / "frontend"
    assets.mkdir()
    (assets / "strategy.js").write_text("import './cards.js';")
    (assets / "cards.js").write_text("// version one")
    monkeypatch.setattr(dashboard, "_FRONTEND", assets)
    urls = []
    for version in ("one", "two"):
        (assets / "cards.js").write_text(f"// version {version}")
        hass = HomeAssistant(str(tmp_path))
        hass.config.components.add("frontend")
        hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(lambda *_: None, [])
        hass.http = HomeAssistantHTTP(hass, None, None, None, None, 8123, [], "modern")
        hass.http.app[KEY_ALLOW_CONFIGURED_CORS] = lambda resource: None
        await async_setup_frontend(hass)
        url = next(iter(hass.data[DATA_EXTRA_MODULE_URL].urls))
        urls.append(url)
        async with TestClient(TestServer(hass.http.app)) as client:
            response = await client.get(url.rsplit("/", 1)[0] + "/cards.js")
            assert await response.text() == f"// version {version}"
    assert urls[0] != urls[1]
