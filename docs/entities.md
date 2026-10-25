# Entity reference

[Documentation index](README.md) · [Guide proxy](epg.md)

Availability depends on receiver capabilities and discovery method. Names below
use US English; native names follow Home Assistant's instance language. Entity
IDs and user-assigned names are preserved. Check **Settings → Devices & services**
for disabled or hidden entities when something is missing from the dashboard.

## Receiver sensors

| Entity | Meaning |
| --- | --- |
| Channel Count | Number of channels in the receiver's lineup |
| Disabled Channels | Disabled lineup channel count; names are available as attributes |
| Favorite Channels | Favorite lineup channel count; names are available as attributes |
| Tuner Count | Total receiver tuner capacity |
| Tuners Available | Idle tuner count; a tuner reporting more than its name is busy, including tuning, streaming, or scanning |
| Lineup Updated | Last successful lineup fetch; HTTP-discovered receivers only |

### Optional guide sensors

These require the XMLTV proxy to be enabled.

| Entity | Meaning |
| --- | --- |
| EPG Status | Cache state, player URLs, counts, coverage, and lineup matching attributes |
| EPG Updated | Last successful guide fetch |
| EPG Coverage End | Latest program end in the cache; coverage may vary by channel |
| EPG Consecutive Failures | Failed refresh attempts since the last success |
| EPG Last Failure | Latest failed attempt, retained after recovery |

See [guide health](epg.md#guide-health-and-program-sensors) for state meanings and
persistence behavior.

## Tuner sensors

| Entity | Meaning |
| --- | --- |
| Tuner status | Idle, in use, scanning, or the tuned channel; additional attributes depend on receiver data |
| Frequency | Tuned frequency |
| Network Rate | Current stream data rate |
| Signal Strength | Received signal level |
| Signal Quality | Reception quality |
| Symbol Quality | Symbol decoding quality |
| Target IP | Stream destination |
| Program | Current cached guide title and program attributes; requires the XMLTV proxy |

The dashboard respects selected sensor units. Signal thresholds are explained
in [reception alerts](dashboard.md#capacity-history-and-reception-alerts).

## Binary sensors

| Entity | Meaning |
| --- | --- |
| Channel Scanning | Scan status, with percentage progress as an attribute |
| All Tuners Busy | Every tuner is tuned or scanning; useful before starting a stream or recording |

## Buttons and controls

| Entity | Purpose |
| --- | --- |
| Channel Scan | Scan using the selected channel source; may interrupt viewing |
| Restart | Restart the receiver, not Home Assistant |
| Refresh Lineup | Fetch the lineup once; HTTP-discovered receivers only |
| Refresh EPG | Fetch the guide now; requires the proxy |
| Rotate EPG URL | Invalidate existing XMLTV/M3U URLs; requires the proxy |
| Channel Sources (select) | Choose the source before starting a channel scan |
| Firmware (update) | Receiver firmware information/update entity |

The bundled dashboard asks for confirmation before scans, receiver restarts, and
URL rotation. Direct button calls and automations are separate from that UI;
consider their effect on active streams and configured players.
