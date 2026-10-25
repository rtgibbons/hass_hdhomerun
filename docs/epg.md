# XMLTV guide and M3U playlist

[Documentation index](README.md) · [Entity reference](entities.md)

The optional guide proxy caches SiliconDust XMLTV data inside Home Assistant and
serves it alongside a matching M3U channel playlist. It is **off by default**.

## Enable and connect a player

1. Enable **XMLTV EPG proxy** in the receiver's integration options.
2. Choose a refresh interval: **3, 6, 12, or 24 hours** (default: 6).
3. Wait for the first background fetch, which starts within five minutes, or
   press **Refresh EPG** to fetch immediately.
4. Open the **EPG status** sensor's attributes and copy `url` for XMLTV and
   `m3u_url` for the matching playlist into your compatible player.

The receiver must provide `DeviceAuth` in its local `discover.json`, and Home
Assistant must reach `https://api.hdhomerun.com/api/xmltv`. Each download reads
the current auth from the device; the integration never stores that auth.

According to [SiliconDust's API documentation](https://github.com/Silicondust/documentation/wiki/XMLTV-Guide-Data),
DeviceAuth changes regularly and is valid for **16–24 hours**. This receiver
credential is separate from the proxy's XMLTV/M3U URL token: do not assume your
player URLs expire on that schedule. Rotate those URLs explicitly when needed.

Set HA's internal or external URL to an address your player can reach. Without
one, the attributes contain only relative paths. No HA bearer token is required:
**the secret in each URL grants access**.

### XML and gzip

| Attribute | Response |
| --- | --- |
| `url` | XML, with HTTP gzip compression when the client advertises `Accept-Encoding: gzip` |
| `gzip_url` | A `.xml.gz` file, served as `application/gzip` without HTTP `Content-Encoding` |
| `m3u_url` | A playlist using the same access token and guide snapshot |

Use `gzip_url` only if the player supports gzip XMLTV files. Both XML formats
serve the same validated snapshot. Compression is prepared off HA's event loop
at refresh/restart and reused; the gzip snapshot adds memory overhead but is not
stored as a second disk copy. Upstream downloads request gzip, but actual
compression depends on SiliconDust's response.

## Playlist matching and lineup refresh

Each matched channel's `tvg-id` uses its XMLTV channel ID. Matching uses virtual
channel numbers from XMLTV `lcn` or display names, then unambiguous channel names.
Unmatched channels remain listed without `tvg-id`; XMLTV IDs are never rewritten.
The playlist's `url-tvg` header points to the XMLTV URL.

Stream URLs point directly to the receiver's local `http://<tuner>:5004/...`
addresses. The player must reach the receiver, not just HA. DRM-protected,
hidden, and disabled channels are omitted. Playlist requests do not trigger
network fetches.

The lineup loads at integration startup and after a channel scan started in HA.
It is **never polled**: legacy receivers use SiliconDust's cloud lineup API
([upstream issue 119](https://github.com/uvjim/hass_hdhomerun/issues/119)). After
changes in another app, press **Refresh Lineup** for one request, or use that
button in an automation. **Lineup Updated** records the last successful fetch.
The button reports an error if no lineup is returned. UDP-discovered devices
do not expose a lineup; the playlist returns 503 until a lineup is available.

Automatic startup/post-scan lineup refreshes and scheduled EPG refreshes also
execute their refresh button actions, so button timestamps include automatic
attempts. Disabling the buttons does not stop automatic fetches; the integration
fetches directly instead. Scheduled guide refreshes are slightly randomized.

## Guide health and program sensors

**EPG status** reports:

| State | Meaning |
| --- | --- |
| `empty` | No validated guide is cached |
| `ready` | A cached guide covers now and the latest refresh has not failed |
| `refresh_failed` | The latest refresh failed, but the cached guide still covers now |
| `expired` | The cached guide's latest program end is in the past |

Attributes include last fetch time, cache age in hours, program/channel counts,
earliest start/latest stop, lineup match counts, and up to 20 unmatched examples.
Feed coverage may differ from the local lineup, especially with multiple tuners.

- **EPG Updated:** last successful fetch.
- **EPG Coverage End:** latest program end in the guide, not a guarantee that
  every channel has coverage until then.
- **EPG Consecutive Failures:** failed downloads, validation, or cache writes
  since the last success; success resets it to zero.
- **EPG Last Failure:** latest failed attempt; recovery does not clear it.

Timestamp sensors are unknown until data exists. They retain last good values
after failure and restore from cache. Failure diagnostics apply to manual and
automatic attempts and persist with the cache. If storage is unavailable, they
continue updating in memory until persistence recovers.

Each tuner also gets a **Program** sensor (**Programme** in British English).
It shows the title airing on the tuned channel, or unknown when idle/unmatched.
Attributes include `channel_id`, `subtitle`, `episode`, `description` (first 500
characters), `start`, `stop`, `next_title`, and `next_start`. No extra requests
are made: the next 48 hours are indexed from the cache at each refresh attempt,
including failed attempts, so cached program lookups work offline.

## Cache and limits

A valid cache continues serving while the receiver or SiliconDust is offline.
Before the first success, XMLTV returns 503. Disabled, unloaded, or rotated URLs
return 404. An invalid, oversized, or failed download never replaces good data.

The proxy validates XMLTV structure, unique channel IDs, program references, and
times. Downloads are chunked and capped at **48 MiB decompressed**; incremental
validation avoids keeping a full parsed XML tree. The complete validated feed
still lives in memory and HA's private atomic storage. Allow extra memory/disk
for serialization and in-progress refreshes.

A 3.31 MiB two-day guide tested with this fork projects to roughly 23 MiB over
14 days for a similar lineup; actual size varies by channels and program detail.
Large entitled feeds can exceed the cap. Check `last_error_type` and logs rather
than assuming a larger limit is safe.

SiliconDust determines the available guide window, typically two days or longer
with eligible DVR service. This integration cannot add missing guide data.

## URL security and retirement

**Treat XMLTV and M3U URLs as passwords.** Anyone with one can read guide/lineup
data. Tokens contain 128 random bits encoded as 22 URL-safe characters. Use HTTPS
across untrusted networks. URLs are visible in HA entity attributes and can
appear in history, proxy logs, and player configuration. Redact them from issues
and screenshots.

**Rotate EPG URL** immediately invalidates all previous XMLTV/M3U links. Update
every player afterward. Upgrades from the former 64-character token format also
generate a new token on the next load; old links are not supported.

Disabling the proxy invalidates URLs while disabled but retains its private
snapshot/token for re-enabling. Removing an integration entry does not delete
its stored guide. If permanently retiring a receiver, back up HA and remove its
`.storage/hdhomerun/epg_<entry_id>` file while HA is stopped; do not delete other
entries' storage.
