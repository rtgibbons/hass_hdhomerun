[![GitHub Release][badge_github_release_version]][github_release_link]
![GitHub Downloads (latest release)][badge_github_release_downloads]
[![GitHub Pre-release][badge_github_prerelease_version]][github_prerelease_link]
![GitHub Downloads (pre-release)][badge_github_prerelease_downloads]

# HDHomeRun

Home Assistant integration for the Silicondust HDHomeRun network tuners.

## Installation

This fork's GitHub default branch is `develop`; it installs directly from
source without a GitHub release ZIP. If the default changes back to `main`,
HACS will request an unavailable release ZIP; the fork owner can restore
`develop` under **Settings → General → Default branch**. In HACS,
open **Custom repositories** from the top-right menu, enter
`https://github.com/rtgibbons/hass_hdhomerun`, select **Integration**, and add
it. Open **HDHomeRun**, select **Download** and choose `develop` (the default
branch), then restart Home Assistant and add the HDHomeRun integration under
**Settings → Devices & services**. HACS does not accept a branch suffix in the
custom repository URL. Home Assistant 2026.1.0 or newer is required by this
fork's HACS metadata. If a previous attempt registered the fork while its
default branch was `main`, refresh HACS repository metadata or remove and
re-add the failed custom repository before downloading. Do not install the
upstream integration alongside this fork under the same `hdhomerun` domain.

Alternatively, add this fork as a custom repository using the button below.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rtgibbons&repository=hass_hdhomerun&category=Integration)

## Description

This integration can be used to get basic information on each HDHomeRun
device in the network. The integration can use the UDP broadcast discovery
protocol, the TCP control protocol and the HTTP API.

### Optional XMLTV guide proxy (fork-specific)

Enable **XMLTV EPG proxy** in the device's integration options. The default
refresh is six hours; 3, 6, 12 and 24 hours are available. Refreshes are
slightly randomized to avoid fixed-time requests to SiliconDust. The first
background fetch starts within five minutes; use the **Refresh EPG** button
to fetch immediately. Automatic refreshes also execute the button action, so
its timestamp shows the last refresh attempt, not just the last manual press.
Check **EPG status** for the last successful fetch and any errors.
This feature is off by default and requires the tuner
to provide `DeviceAuth` in its local `discover.json`, and HA to reach
`https://api.hdhomerun.com/api/xmltv`. The integration requests gzip and reads
the current auth immediately before each download; it never stores the auth.

The **EPG status** sensor exposes `url` and `gzip_url` attributes. Set HA's
internal or external URL to an address UHF can reach (otherwise this attribute
is only a relative path), then enter that full URL as UHF's XMLTV source. No HA
bearer token is needed. A valid cache serves even when the tuner or SiliconDust
is temporarily offline. Until the first successful refresh the URL returns 503;
disabled/unloaded/rotated URLs return 404. The status sensor shows `empty`,
`ready`, `refresh_failed`, or `expired`, plus last fetch time, cache age in
hours, programme/channel counts, earliest start/latest stop, and how many
lineup channels match an XMLTV channel ID, with up to 20 unmatched examples.
Feed coverage and lineup can differ from the local device, particularly with
multiple tuners.

Two diagnostic timestamp sensors make freshness visible without opening the
status attributes: **EPG Updated** is the last successful guide fetch, and
**EPG Coverage End** is the latest programme end time in the cached guide
(not a guarantee of coverage for every channel). Both are unknown until their
timestamps are available, use the restored cache after a restart, and retain
their last good values if a refresh fails. The existing `fetched_at` and
`coverage_end` status attributes remain available.

**EPG Consecutive Failures** counts failed refresh attempts, including download,
validation and cache-write failures, and resets to zero after a successful
refresh. **EPG Last Failure** records the latest failed attempt and is unknown
until the first failure; a later success does not clear it. Both are diagnostic
sensors, apply to manual and automatic refreshes, and are saved with the guide
cache across restarts. If storage is unavailable, failure history still updates
in memory but cannot be persisted until storage recovers.

The normal URL serves XML and uses HTTP gzip compression when the client
advertises `Accept-Encoding: gzip`. The `gzip_url` appends `.xml.gz` and always
serves a gzip file (`application/gzip`, without HTTP `Content-Encoding`). Use
that option only with players that support gzip XMLTV files. Both formats
serve the same validated snapshot and share the same access token. Compression
is prepared off the HA event loop on refresh/restart and reused for requests;
the gzip snapshot adds memory overhead but is not stored as a second disk copy.
Upstream downloads already request gzip; actual compression depends on
SiliconDust's response, and the size limit still applies after decompression.

The sensor's `m3u_url` attribute is a matching M3U playlist that uses the same
secret token. Each lineup channel's `tvg-id` is set to its XMLTV channel ID, so
UHF, Channels, Jellyfin or Plex can pair the playlist with the guide without
manual mapping. Channels are matched by virtual channel number (the XMLTV
`lcn` or a display name), then by an unambiguous channel name. Unmatched
channels are still listed, without `tvg-id`. The playlist's `url-tvg` header
points at the XMLTV URL. Stream URLs are the tuner's own local
`http://<tuner>:5004/...` addresses, so the client must reach the tuner
directly. DRM-protected, hidden and disabled channels are omitted. Serving the
playlist makes no requests. The lineup is read when the integration loads and
again when a channel scan started from HA finishes; it is never polled, because
legacy tuners' lineup URL is SiliconDust's cloud API (see
[upstream issue 119](https://github.com/uvjim/hass_hdhomerun/issues/119)).
After a scan or channel changes made in another app, press **Refresh Lineup**
(one request per press; it also works as an automation action). The **Lineup
Updated** sensor shows when the lineup was last fetched successfully, and the
button reports an error if the tuner did not return one. The playlist
returns 503 until a lineup is available; UDP-discovered devices
do not expose one. XMLTV channel IDs themselves are not rewritten.

Startup and post-scan lineup refreshes also execute **Refresh Lineup**, updating
its timestamp. Disabling either refresh button does not disable automatic
fetches; the integration fetches directly when its button is disabled.

With the proxy enabled, each tuner also gets a **Programme** sensor. Its state
is the title of the programme airing on the tuned channel, from the cached
guide, and its attributes are `channel_id`, `subtitle`, `episode`,
`description` (first 500 characters), `start`, `stop`, `next_title` and
`next_start`. It is unknown when the tuner is idle or the channel has no
matching guide entry. No extra requests are made: the next 48 hours of
programmes are indexed in memory at each refresh attempt, including failed
ones, so the sensor keeps working from the cache while offline.

**Treat the URLs as passwords:** anyone who obtains them can read the guide and
the lineup. Tokens contain 128 random bits encoded as 22 URL-safe characters.
On updating from the former 64-character format, the next integration load
generates a new token; copy the new URLs into your player. Old URLs are not
supported. Use HTTPS if UHF connects across an untrusted network. The URLs are
visible to HA users via entity attributes and may appear in HA history,
reverse-proxy access logs, or UHF configuration. Do not publish them in
screenshots or issue reports. The **Rotate EPG URL** button immediately
invalidates the previous XMLTV and M3U URLs; update UHF after rotating.
Disabling this option invalidates the URLs while disabled but retains the
private HA storage snapshot/token for re-enable. Removing an entry does not
automatically delete its stored guide; remove its
`.storage/hdhomerun/epg_<entry_id>` file manually if retiring the device.
SiliconDust determines the available guide window (typically two days, or
longer with eligible DVR service); this proxy cannot add missing guide data.

The guide is validated as XMLTV (`tv`, uniquely identified channels and
programmes with valid references/times) and capped at 48 MiB decompressed.
The HTTP download is chunked and stops at the cap; validation parses
incrementally rather than retaining a full XML tree. The complete validated
guide is still kept in memory and in HA's private, atomic storage so UHF can
retrieve it while offline; allow additional memory and disk headroom for
serialization and an in-progress refresh. An invalid, oversized or failed
download never replaces the last good cache. The 3.31 MiB two-day guide tested
with this fork suggests roughly 23 MiB at 14 days for a similar lineup, but
real guide size depends on channels and programme detail. A larger entitled
feed may still exceed 48 MiB; check `last_error_type` and the HA logs before
considering a higher limit or a disk-backed streaming cache.

## Entities Provided

Where applicable the sub-items in the list detail the additional attributes
available. All entities may not be available to you depending on how the
device was discovered and what its capabilities are.

### Binary Sensors

| Location | Name | Enabled by default | Additional Information |
|---|---|:---:|---|
| Device | Channel Scanning | ✔️ | Percentage progress of the channel scan |
| Device | All Tuners Busy | ✔️ | On when every tuner is tuned or scanning; useful to warn before a recording or stream would fail |

### Button

| Location | Name | Enabled by default | Comments |
|---|---|:---:|---|
| Device | Channel Scan | ✔️ | Requires the source to be selected first (see [here](#select)) |
| Device | Restart | ✔️ |  |
| Device | Refresh Lineup | ✔️ | Re-reads the channel lineup once (it is never polled). HTTP-discovered devices only |

### Select

| Location | Name | Enabled by default | Comments |
|---|---|:---:|---|
| Device | Channel Sources | ✔️ | Selects the channel source to be used when carrying out a channel scan |

### Sensors

| Location | Name | Enabled by default | Primary value | Additional Information | Comments |
|---|---|:---:|---|---|---|
| Device | Channel Count | ✔️ | Number of channels currently tuned on the device | | |
| Device | Disabled Channels | ✔️ | Number of channels marked as disabled in the channel list | List of channel names | |
| Device | EPG Updated | ✔️ | When the guide was last fetched successfully | | Only with the XMLTV EPG proxy enabled |
| Device | EPG Coverage End | ✔️ | Latest programme end time in the cached guide | | Only with the XMLTV EPG proxy enabled; coverage may vary by channel |
| Device | EPG Consecutive Failures | ✔️ | Failed refresh attempts since the last successful fetch | | Only with the XMLTV EPG proxy enabled |
| Device | EPG Last Failure | ✔️ | When the latest refresh failure occurred | | Only with the XMLTV EPG proxy enabled; retained after recovery |
| Device | Favourite Channels | ✔️ | Number of channels marked as favorites in the channel list | List of channel names | |
| Device | Lineup Updated | ✔️ | When the channel lineup was last fetched successfully | | HTTP-discovered devices only |
| Device | Tuner Count | ✔️ | Number of tuners the device has | | |
| Device | Tuners Available | ✔️ | Number of tuners that are idle | | A tuner counts as busy when it reports anything beyond its name (tuned, streaming or scanning) |
| Tuner | Tuner X | ✔️ | Status of the tuner; `Idle`, `In use`, `Scanning` or the channel being watched | Frequency, signal strength, signal quality, symbol quality, network rate and target IP (as applicable) | X is the tuner number. |
| Tuner | Frequency | ✔️ | | | |
| Tuner | Network Rate | ✔️ | | | |
| Tuner | Signal Quality | ✔️ | | | |
| Tuner | Symbol Strength | ✔️ | | | |
| Tuner | Target IP | ✔️ | | |  |
| Tuner | Programme | ✔️ | Title of the programme airing on the tuned channel | Channel ID, subtitle, episode, description, start, stop, next title and next start | Only with the XMLTV EPG proxy enabled |

### Update

| Location | Name | Enabled by default | Comments |
|---|---|:---:|---|
| Device | Firmware | ✔️ | |

# Setup

## `Add Integration` button

If adding the integration by clicking the `Add Integration` button the
following information will be requested.

![Initial Setup Screen](images/step_user.png)

* `Host`: The IP of an HDHomeRun device on the network. Leave
  blank to carry out discovery.

  * If you provide a valid IP address, and you will be prompted for
    a friendly name.

    ![Initial Setup Screen](images/friendly_name.png)

### HTTP/UDP Discovery

This section is only applicable if you did not provide a host in the
[Add Integration](#add-integration-button) section.

![HTTP/UDP Discovery](images/http_udp_discovery.png)

Click `NEXT` and you will be prompted for a friendly name.

![Initial Setup Screen](images/friendly_name.png)

### Setup Complete

On successful set up the following screen will be seen detailing the device.

![Final Setup Screen](images/setup_finish.png)

## SSDP Discovery

The integration can also detect the HDHomeRun devices on the network using
SSDP. When found they will look like this on your devices screen.

![Initial Setup Screen](images/ssdp_discovery.png)

Clicking `CONFIGURE` you will be prompted for a friendly name.

![Initial Setup Screen](images/friendly_name.png)

## Configurable Options

It is possible to configure the following options for the integration.

### Timeouts

![Configure Options](images/config_timeouts.png)

* `Scan Interval`: the frequency of updates for the sensors, default `300s`
* `Tuner status update`: the frequency of updates for tuners, default `10s`

### Options

![Configure Options](images/config_options.png)

* `Channel logo path` - the path to a directory containing channel logos,
  e.g. `/local/channel_logos`. The default is to have no logo. If previously
  set, you can clear this option by just entering a space

You can also select which format should be used for the sensor. The
default is `Channel name`.

_This setting is only effective when a tuner is actively tuned to a channel._

## Dashboard

The integration includes an optional HDHomeRun dashboard and its cards. There
are no separate card downloads and no sidebar dashboard is created automatically.

After installing or updating the integration, restart Home Assistant and refresh
your browser. In Home Assistant 2026.5 or later, open **Settings → Dashboards →
Add dashboard → Community dashboards → HDHomeRun**. Add it once and choose
whether to show it in your sidebar.

On earlier supported Home Assistant versions, create a new blank dashboard and
replace its raw configuration with:

```yaml
strategy:
  type: custom:hdhomerun
```

The managed dashboard discovers the integration's receivers and tuners from
the entity registry, including renamed entities. Each receiver has its own
overview and maintenance subview. Missing, disabled, or hidden entities are
omitted; enable optional diagnostic entities in **Settings → Devices & services**
if you want to display them. The dashboard does not enable entities itself.
EPG details appear only when the XMLTV proxy is enabled. Maintenance actions
require confirmation; opening a dashboard never starts a scan or restarts a device.

### Updates and customization

Dashboard layout and card improvements ship with integration updates. After a
normal HACS update, restart Home Assistant and refresh the browser to load the
new bundled assets. You do not need to delete and re-add the dashboard. Existing
user-created dashboards, including dashboards using other cards, are not changed.
If you **Take control** of the generated dashboard, its layout becomes your own
static configuration and no longer receives generated layout updates; bundled
cards still update. Keep the strategy configuration for managed layout updates.

Dashboard text follows each viewer's language and clock preferences; `en` uses
US English and `en-GB` uses British English. Native entity names follow Home
Assistant's instance language. Entity IDs, unique IDs, and user-assigned names
are preserved, including legacy spelling when generating new entity IDs.
Older frontends without strategy regeneration support (including HA 2026.2)
need a browser reload after changing language to update generated section labels.

### Capacity history and reception overlays

The full-width capacity chart uses whole-number tuner counts and shows 24, 36,
or 48 hours according to the chart's available width. History requires Home
Assistant's History/Recorder integrations and retention covering that period.
Unavailable data produces gaps rather than invented readings.

Reception warnings and errors are translucent regions behind the capacity lines.
Select a region (or focus it and press Enter/Space) for readings and timestamps.
Idle and unknown readings are excluded. Signal quality warns below 70% and
errors below 50%; symbol quality errors below 100%.

Signal-strength thresholds depend on the source. They are not applied by default,
because the integration cannot reliably infer the source. To enable them, edit
the managed dashboard's raw strategy configuration, setting `signal_profile` to
`antenna` or `cable`:

```yaml
strategy:
  type: custom:hdhomerun
  signal_profile: antenna
```

For antenna, strength warns below 75% and errors below 50%; for cable, it warns
below 90% and errors below 80%. These bands follow
[SiliconDust's signal-color implementation](https://github.com/Silicondust/libhdhomerun/blob/master/hdhomerun_device.c),
not a guarantee of picture quality. Each shading interval reflects the worst
observed active-tuner condition. The network-rate bar is a labeled 20 Mbit/s
display scale (converted to your sensor's selected unit), not a bandwidth limit.

## Troubleshooting

### Debug Logging

Debug logging can be enabled in Home Assistant using the [`logger`
integration](https://www.home-assistant.io/integrations/logger/).

```yaml
logger:
  default: warning
  logs:
    custom_components.hdhomerun: debug
```

### Diagnostics Integration

Starting with Home Assistant 2022.2, a new diagnostics integration can be
used to provide troubleshooting for integrations.

The highlighted area in the image below shows where the link for downloading
diagnostics can be found.

![Diagnostics](images/diagnostics.png)

An [example output](examples/diagnostics_output.json) can be found in this repo.

[badge_github_release_version]: https://img.shields.io/github/v/release/rtgibbons/hass_hdhomerun?display_name=release&style=for-the-badge&logoSize=auto
[badge_github_release_downloads]: https://img.shields.io/github/downloads/rtgibbons/hass_hdhomerun/latest/total?style=for-the-badge&label=downloads%40release
[badge_github_prerelease_version]: https://img.shields.io/github/v/release/rtgibbons/hass_hdhomerun?include_prereleases&display_name=release&style=for-the-badge&logoSize=auto&label=pre-release
[badge_github_prerelease_downloads]: https://img.shields.io/github/downloads-pre/rtgibbons/hass_hdhomerun/latest/total?style=for-the-badge&label=downloads%40pre-release
[github_release_link]: https://github.com/rtgibbons/hass_hdhomerun/releases/latest
[github_prerelease_link]: https://github.com/rtgibbons/hass_hdhomerun/releases
