# Documentation

[Project overview](../README.md)

Start with installation, add the optional dashboard, then enable the guide proxy
only if your players need it.

| Guide | Purpose |
| --- | --- |
| [Installation and configuration](installation.md) | Requirements, HACS, discovery, and integration options |
| [Dashboard](dashboard.md) | Setup, managed updates, customization, and reception alerts |
| [XMLTV guide and M3U playlist](epg.md) | Guide refreshes, player URLs, cache behavior, and security |
| [Entity reference](entities.md) | Available entities and their meanings |
| [Troubleshooting](troubleshooting.md) | Common problems, diagnostics, and logging |
| [2027.0.0 release notes (unreleased)](releases/2027.0.0.md) | First fork candidate, upgrade guidance, rollback, and outstanding gates |
| [Release and HACS submission](releasing.md) | Maintainer checklist, licensing, validation, and publishing gates |

The first fork candidate is **unreleased**, with publication blocked on
[licensing permissions](releasing.md#licensing-status). Use `main` only for
current custom-install testing; `develop` is opt-in development. After
publication, prefer published release tags through the HACS custom repository.

The [screenshot collection](../images/dashboard/README.md) includes desktop,
mobile, maintenance, and British English views, with capture provenance.
