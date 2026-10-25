# Troubleshooting

[Documentation index](README.md) · [Installation](installation.md)

## Dashboard missing from the picker

1. Confirm HACS downloaded the intended fork version: currently `main` for
   custom-install testing, or `develop` only for opt-in development. After
   publication, use a published release tag for normal installations.
2. Restart Home Assistant after installing/updating the integration.
3. **Hard refresh the browser.** An already-open tab can retain old frontend
   registration even when the server files are current.
4. On HA 2026.5 or later, look under **Settings → Dashboards → Add dashboard →
   Community dashboards → HDHomeRun**. Earlier supported versions use the
   [blank-dashboard strategy](dashboard.md#add-the-dashboard).

There is no automatic prompt and no automatically created sidebar entry.

## Missing entities or stale labels

- Confirm the receiver is configured under **Settings → Devices & services**.
- Check whether the entities are disabled or hidden; the dashboard omits them
  and does not enable them automatically.
- Guide/program entities require the optional XMLTV proxy.
- Discovery method and receiver capabilities determine which entities exist.
- Native entity names follow the HA instance language. Dashboard text follows
  the viewer's language, except user-provided names and receiver program titles.
- Reload older frontends, including HA 2026.2, after a language change to refresh
  generated dashboard labels.

## History missing or shorter than expected

Confirm History/Recorder are enabled, source entities are not excluded from
recording, and retention covers the desired time. New entities cannot show
readings from before they were recorded. Chart width selects 24/36/48 hours;
see [capacity history](dashboard.md#capacity-history-and-reception-alerts).

## Guide or player problems

- **No guide yet / 503:** wait for the initial fetch or press **Refresh EPG**.
  A playlist also needs a successfully fetched lineup.
- **404:** confirm the integration is loaded, the proxy is enabled, and the URL
  has not rotated. Copy the current URL privately from EPG Status.
- **Relative URL only:** configure an HA internal/external URL reachable by the
  player. The player must also reach the receiver for direct stream URLs.
- **Refresh failed:** check EPG Status's `last_error_type`, failure diagnostics,
  and logs. HA needs access to the receiver and SiliconDust's XMLTV endpoint.
- **Missing channels or programs:** compare coverage and lineup-match attributes.
  Press **Refresh Lineup** after changes outside HA; the lineup is not polled.
  SiliconDust controls guide availability, and coverage can differ by channel.

See [guide proxy behavior and security](epg.md) before changing player URLs.

## Collect diagnostics

Download diagnostics from the integration/device menu in
**Settings → Devices & services**.

![Diagnostics download location](../images/diagnostics.png)

An [example diagnostics output](../examples/diagnostics_output.json) is included
in this repository. It illustrates an older export format and has been manually
sanitized; it is not evidence that every field in a new export is safe to share.
The current exporter redacts the entire `processed_datagram`, in addition to
named authentication/device fields. **Remove `processed_datagram` from older
exports before sharing:** raw discovery packets and numeric tags can contain
the same values even when named fields are redacted. Still review every download
for XMLTV/M3U URL tokens, credentials, and private network information before
including it in logs, screenshots, or issues.

For fork-specific bugs, open an
[issue here](https://github.com/rtgibbons/hass_hdhomerun/issues), including:

- Home Assistant and integration versions, plus browser version for UI issues.
- Receiver model and discovery method (HTTP/UDP/SSDP).
- Reproduction steps, expected result, and actual result.
- Relevant redacted diagnostics or log excerpts.

## Debug logging

Enable debug logging using Home Assistant's
[`logger` integration](https://www.home-assistant.io/integrations/logger/):

```yaml
logger:
  default: warning
  logs:
    custom_components.hdhomerun: debug
```

Reproduce the issue, collect only the relevant redacted output, then disable
debug logging when finished.
