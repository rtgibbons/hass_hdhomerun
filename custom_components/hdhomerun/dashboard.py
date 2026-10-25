"""Serve the opt-in dashboard without modifying users' Lovelace storage."""

from hashlib import sha256
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

_FRONTEND = Path(__file__).parent / "frontend"


def _asset_path() -> str:
    """Version the entire module tree so relative imports update together."""
    digest = sha256()
    for path in sorted(_FRONTEND.glob("*.js")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return f"/hdhomerun/frontend/{digest.hexdigest()[:16]}"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Load the strategy picker entry, not a dashboard or sidebar panel."""
    if "frontend" not in hass.config.components:
        return
    url = await hass.async_add_executor_job(_asset_path)
    await hass.http.async_register_static_paths([
        StaticPathConfig(url, str(_FRONTEND), cache_headers=True)
    ])
    frontend.add_extra_js_url(hass, f"{url}/strategy.js")
