# HDHomeRun for Home Assistant

[![Validate](https://github.com/rtgibbons/hass_hdhomerun/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/rtgibbons/hass_hdhomerun/actions/workflows/validate.yml?query=branch%3Amain)
[![Latest release](https://img.shields.io/github/v/release/rtgibbons/hass_hdhomerun)](https://github.com/rtgibbons/hass_hdhomerun/releases)
[![Home Assistant minimum: 2026.1.0](https://img.shields.io/badge/Home_Assistant-2026.1.0%2B-18BCF2?logo=homeassistant&logoColor=white)](docs/installation.md#requirements)
[![HACS: Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white)](docs/installation.md#install-through-hacs)

Monitor your SiliconDust HDHomeRun network tuners in Home Assistant, with live
tuner statistics, an optional managed dashboard, and a cached XMLTV guide proxy.

This is the **maintained fork by
[rtgibbons](https://github.com/rtgibbons)** of
[uvjim/hass_hdhomerun](https://github.com/uvjim/hass_hdhomerun), with additional
dashboard, guide, and diagnostic features. The original integration was developed
by [uvjim](https://github.com/uvjim) and its contributors. This is a custom
integration, not a Home Assistant app/add-on or an official SiliconDust product.

> **Release preparation:** the first fork candidate, **2026.10.1**, is
> **unreleased**. Publication remains blocked on
> [licensing permissions](docs/releasing.md#licensing-status); release gates have
> not all passed. The live release badge has no release to display until one is
> published; it is not a badge for the candidate. HACS installation is via a
> **custom repository**, not the default HACS list.

## Features

- **Receiver and tuner monitoring:** channel, program, signal strength and
  quality, network rate, available tuners, and firmware information.
- **Bundled dashboard:** compact tuner cards, guide health, responsive capacity
  history, and reception warning/error overlays. No separate card installs.
- **Optional XMLTV and M3U proxy:** cached guide data and a matching channel
  playlist for compatible players, with freshness and failure diagnostics.
- **Device controls:** refresh the lineup or guide, scan channels, and restart
  the receiver. Dashboard maintenance actions ask for confirmation.
- **English localization:** US and British display text, with Home Assistant
  language, clock, and sensor-unit preferences respected.

Available entities depend on receiver capabilities and discovery method.

## Quick start

Requires **Home Assistant 2026.1.0 or later**,
[HACS](https://www.hacs.xyz/), and network access to your HDHomeRun receiver.

1. In HACS, open **Custom repositories** and add
   `https://github.com/rtgibbons/hass_hdhomerun` as an **Integration**.
2. For current custom-install testing, download **HDHomeRun for Home Assistant**,
   choosing `main`, then restart Home Assistant. After publication, prefer a
   published release tag; `develop` is opt-in development only.
3. Open **Settings → Devices & services → Add integration** and search for
   **HDHomeRun for Home Assistant**. Enter the receiver's IP address, or leave
   it blank to discover receivers.
4. To add the optional dashboard, follow the [dashboard setup](#dashboard) below.

> **Install only one HDHomeRun custom integration.** This fork and upstream use
> the same `hdhomerun` domain and cannot be installed side-by-side. Existing users
> should back up Home Assistant before switching sources.

[Installation and configuration guide](docs/installation.md)

## Dashboard

Add the dashboard once; future integration updates deliver its managed layout
and cards. Each receiver gets an overview and a maintenance subview. Nothing is
automatically added to your sidebar, and installation does not show a prompt.

![HDHomeRun dashboard with compact tuner cards and 48-hour capacity history](images/dashboard/desktop-48h.png)

*Actual Home Assistant capture with synthetic receiver and history data.*

On **Home Assistant 2026.5 or later**, restart after installation, **hard refresh
your browser**, then open **Settings → Dashboards → Add dashboard → Community
dashboards → HDHomeRun**. Choose whether to show it in the sidebar.

Earlier supported versions can use the
[blank-dashboard configuration](docs/dashboard.md#add-the-dashboard).

The full-width history chart adapts to 24, 36, or 48 hours of available space,
with integer tuner counts and translucent reception alerts. Keeping the
dashboard managed preserves layout updates; **Take control** creates a static,
user-owned layout instead.

[Dashboard guide: customization, updates, and alert thresholds](docs/dashboard.md)

## Documentation

| Guide | What you will find |
| --- | --- |
| [Installation and configuration](docs/installation.md) | HACS setup, discovery, polling, and receiver options |
| [Dashboard](docs/dashboard.md) | Add-once workflow, managed vs. custom layouts, history, and localization |
| [XMLTV guide and M3U playlist](docs/epg.md) | Player setup, cache behavior, diagnostics, and URL security |
| [Entity reference](docs/entities.md) | Sensors, buttons, controls, and capability requirements |
| [Troubleshooting](docs/troubleshooting.md) | Browser refresh, missing entities, guide failures, and debug logs |
| [2026.10.1 release notes (unreleased)](docs/releases/2026.10.1.md) | Candidate features, upgrade steps, rollback, and publication blockers |
| [Release preparation](docs/releasing.md) | Branch model, validation, licensing research, and publication gates |

See the [documentation index](docs/README.md) for a suggested reading order.

## Support and upstream

Report fork-specific problems in
[this repository's issue tracker](https://github.com/rtgibbons/hass_hdhomerun/issues).
Include your Home Assistant version, receiver model, discovery method, and
redacted diagnostics. **Never publish XMLTV/M3U URLs or receiver authentication
values**; see [safe troubleshooting](docs/troubleshooting.md#collect-diagnostics).

This fork is maintained by [rtgibbons](https://github.com/rtgibbons); direct
fork-specific support requests here rather than to the upstream maintainer.
The original integration's history and contributors remain available in the
[upstream repository](https://github.com/uvjim/hass_hdhomerun). Attribution does
not imply upstream endorsement of this fork.
