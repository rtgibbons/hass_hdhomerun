# Dashboard screenshots

Captured on October 25, 2026 for future documentation updates. These show the
bundled HDHomeRun dashboard in an actual local Home Assistant 2026.2.3 instance
with frontend 20260128.6, rendered in Chromium.

All receiver names, readings, program titles, timestamps, and recorded history
are synthetic test data. These are rendered UI captures, not design mockups or
captures of a user's installation. No maintenance actions were executed.

| File | State |
| --- | --- |
| [desktop-48h.png](desktop-48h.png) | Desktop overview; 48-hour adaptive history, active and idle tuners, and warning/error shading. |
| [mobile-24h.png](mobile-24h.png) | 390px-wide overview; 24-hour adaptive history. Cropped only to remove empty space beneath the final card. |
| [maintenance.png](maintenance.png) | Device diagnostics and protected maintenance actions. |
| [en-gb-24-hour-clock.png](en-gb-24-hour-clock.png) | British English after reload: Programme, Favourites, and a 24-hour clock. The history window remains 48 hours. |

The mobile capture's long device title is truncated by Home Assistant's normal
header layout. Older frontends such as this test version require a reload after
changing language to update strategy-generated section labels.

These are the final documentation-ready HA captures from this validation round.
Intermediate captures, the stale-label reproduction, and the separately labeled
overlay interaction fixture are intentionally excluded.
