# Installation and configuration

[Documentation index](README.md) · [Next: Dashboard](dashboard.md)

## Requirements

- Home Assistant **2026.1.0 or later**, as required by this fork's HACS metadata.
- [HACS](https://www.hacs.xyz/) for the installation workflow below.
- A SiliconDust HDHomeRun receiver reachable from Home Assistant. Discovery uses
  SSDP or UDP; available features depend on the device's TCP/HTTP capabilities.
- Internet access for the optional SiliconDust XMLTV feed. Basic local tuner
  monitoring does not require enabling the guide proxy.

This is a custom integration, not a Home Assistant app/add-on. This fork and
[upstream](https://github.com/uvjim/hass_hdhomerun) share the `hdhomerun` domain:
install one, not both. Back up Home Assistant before switching sources.

## Install through HACS

The first fork candidate, **2026.10.1**, is **unreleased**. Publication is still
blocked on [licensing permissions](releasing.md#licensing-status). The steps
below describe custom-install testing, not a published or default-listed release.

1. Open HACS and choose **Custom repositories** from the top-right menu.
2. Enter `https://github.com/rtgibbons/hass_hdhomerun`, select **Integration**,
   and add it. Do not append a branch name to the repository URL.
3. Open **HDHomeRun for Home Assistant**, select **Download**, and choose
   `main` for current testing. Choose `develop` only if you explicitly want
   ongoing development changes.
4. Restart Home Assistant.
5. Add the receiver as described below, then optionally
   [add the dashboard](dashboard.md#add-the-dashboard).

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rtgibbons&repository=hass_hdhomerun&category=Integration)

After publication, normal HACS installs and updates use published release tags.
The stable/default fork branch is `main`; branch selection is currently useful
for testing before a release exists. The `uvjim` branch preserves upstream-only
history and is not the fork installation target.

With `zip_release: false`, HACS downloads repository source at the selected
release tag or branch, not an attached `hdhomerun.zip`. If HACS requests an
unavailable release ZIP, refresh its repository metadata or remove and re-add
the failed custom repository. A HACS Custom badge does not mean this fork is
included in HACS's default list.

## Manual installation

Once a release is published, its attached `hdhomerun.zip` is an alternative to
HACS. It contains integration files such as `manifest.json` at the **ZIP root**,
not a containing `custom_components/hdhomerun` directory. Extract those files
into `<config>/custom_components/hdhomerun/`, then restart Home Assistant. Do not
extract them directly into `<config>/custom_components/`.

Before publication there is no fork release ZIP to download. For manual source
testing, copy only the repository's `custom_components/hdhomerun/` directory to
the same location under your Home Assistant configuration. Do not mix files
from different versions or install this fork alongside upstream.

## Add a receiver

Open **Settings → Devices & services → Add integration** and search for
**HDHomeRun for Home Assistant**. Older screenshots below use the previous
display name; the integration domain remains `hdhomerun`.

![Receiver host entry](../images/step_user.png)

- Enter the receiver's IP address to target it directly.
- Leave **Host** blank to discover receivers, then select the desired device.

![Discovered receiver selection](../images/http_udp_discovery.png)

Choose a friendly name when prompted. Repeat for additional receivers.

![Friendly name entry](../images/friendly_name.png)

Devices discovered through SSDP can also appear automatically under
**Settings → Devices & services**. Choose **Configure** and provide a friendly
name to finish setup.

![SSDP discovery](../images/ssdp_discovery.png)

After setup, Home Assistant lists the receiver and its available entities.

![Completed receiver setup](../images/setup_finish.png)

## Integration options

Open the HDHomeRun entry's configuration/options in
**Settings → Devices & services**.

### Polling intervals

| Option | Default | Purpose |
| --- | --- | --- |
| Scan interval | 300 seconds | General receiver information updates |
| Tuner status update | 10 seconds | Active tuner status updates |

These control polling, not channel scanning or the separate EPG refresh timer.

![Polling interval options](../images/config_timeouts.png)

### Channel display and guide

- **Channel logo path:** directory containing channel logos, for example
  `/local/channel_logos`. No logo is configured by default. Clear a previous
  value by entering a space.
- **Channel format:** channel name (default), channel number, or number and name.
  This applies while a tuner is actively tuned.
- **XMLTV EPG proxy:** off by default. Enable it to expose guide, playlist, and
  program entities. Choose a refresh interval of 3, 6, 12, or 24 hours (default:
  6). See the [guide proxy documentation](epg.md) before sharing player URLs.

![Channel display options](../images/config_options.png)

Older setup screenshots may not show recently added guide options.

## Update

Back up Home Assistant before updating. After publication, select the desired
published release in HACS; branch testers should confirm their selected branch
before downloading. Download the update, restart Home Assistant, and refresh
your browser.
Use a **hard refresh** if the dashboard picker or cards still show old behavior.
The managed dashboard updates without deleting and re-adding it; a layout you
have [taken control of](dashboard.md#updates-and-customization) stays user-owned.

## Switch from upstream or roll back

1. Create a full Home Assistant backup and record the installed repository,
   version/tag or branch commit, integration options, and dashboard settings.
   Save any user-owned dashboard YAML separately.
2. Switch the HACS repository source to the intended fork or upstream repository;
   do not keep two downloads managing `custom_components/hdhomerun/`. Keep the
   existing integration entries unless migration instructions specifically
   require removing them. The shared domain is intended to preserve identity,
   not a guarantee that every version's configuration is downgrade-compatible.
3. Install the chosen version's complete integration directory, replacing the
   old directory rather than overlaying files. For manual installs, preserve
   your backup outside that directory. Restart Home Assistant and hard refresh
   browsers, then check existing receivers, entities, options, and dashboards.
4. To roll back, reinstall the previously recorded release/source version and
   restart. If configuration or dashboard state is incompatible, restore the
   pre-upgrade Home Assistant backup. Upstream does not provide this fork's
   managed dashboard or guide features; remove or restore dependent dashboards
   and player settings as appropriate.

Never install upstream and this fork side-by-side: both use `hdhomerun`.
See the [unreleased candidate notes](releases/2026.10.1.md) before switching.
