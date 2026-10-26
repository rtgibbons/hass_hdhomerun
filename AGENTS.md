# Repository guide for coding agents

## Project and layout

This is rtgibbons' maintained fork of uvjim/hass_hdhomerun, a Home Assistant
custom integration for SiliconDust HDHomeRun receivers. It uses asynchronous
Python for receiver monitoring and an optional XMLTV/M3U proxy, plus bundled
JavaScript dashboard components. Preserve attribution to uvjim and contributors.

- `custom_components/hdhomerun/`: all installed integration runtime files.
  `__init__.py` owns setup, coordinators, and entity lifecycle; platform modules
  expose sensors, buttons, selects, updates, and binary sensors.
- `pyhdhr/` inside the integration: bundled HTTP/TCP/UDP receiver client.
- `epg.py`: guide fetching, caching, and playlist/guide HTTP views.
- `dashboard.py` and `frontend/`: asset registration, dashboard strategy, cards,
  and frontend localization. Assets are served by HA, not a separate web app.
- `translations/`: Home Assistant translations (`en` and `en-GB`).
- `tests/`: Python pytest tests and Node built-in test-runner suites (`.mjs`).
- `docs/`: installation, dashboard, entities, guide proxy, and release guidance.
  `examples/` and `images/` contain public examples and documentation assets.
- `.github/workflows/`: code validation, HACS eligibility, and release packaging.

## Local setup

Use Python 3.13, matching CI, and Node 24 or 26 for dashboard tests. There is no
`package.json`, npm install step, frontend compilation, or standalone dev server.
Run commands from the repository root.

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-test.txt 'defusedxml>=0.7.1'
```

`requirements-test.txt` pins HA and test tools. Runtime dependencies are declared
in `custom_components/hdhomerun/manifest.json`; keep setup instructions aligned
when those requirements change. `.agents/setup` and `.agents/resume` are Amp orb
environment scripts, not general local setup commands.

## Checks

```bash
.venv/bin/ruff check custom_components tests --output-format github
.venv/bin/python -m pytest -q tests
node --test tests/test_dashboard*.mjs
actionlint
npx --yes markdownlint-cli README.md AGENTS.md 'docs/**/*.md'
git diff --check
```

Install `actionlint` separately when editing workflows. Markdown lint runs via
`npx`; it does not require a project npm dependency. CI exercises dashboard tests
on both Node 24 and 26. To focus Python checks, use a test path or `-k`, for
example `.venv/bin/python -m pytest -q tests/test_diagnostics.py`.

With Docker available, validate the integration manifest locally with Hassfest:

```bash
docker run --rm -v "$PWD:/github/workspace:ro" ghcr.io/home-assistant/hassfest
```

On ARM hosts, use `--platform linux/amd64` if the image needs emulation.
HACS eligibility also checks live GitHub metadata; local tests alone cannot
establish that it passes. Do not bypass validators to remove warnings.

## Development conventions

- Follow existing HA async/coordinator and entity patterns. Do not block HA's
  event loop or introduce a second polling lifecycle for existing receiver data.
- Follow `pyproject.toml` for Ruff rules and existing JavaScript conventions.
  Keep changes scoped; avoid reformatting unrelated inherited code.
- Preserve the `hdhomerun` domain, existing entity identities, and configuration
  compatibility unless a migration is explicitly part of the task. The fork and
  upstream cannot be installed side-by-side under the same domain.
- Keep runtime files under the integration directory. HACS installs the release
  asset `hdhomerun.zip` (`zip_release: true`), with runtime files at the ZIP root.
- Update HA translations and frontend localization when changing visible text.
  Discover dashboard entities through registries rather than fixed entity IDs.
- Extend existing tests for observable behavior. Python tests cover HA/server
  behavior; Node tests cover frontend generation and cards without a full browser.
  For appearance changes, also render and inspect affected states in disposable
  HA; Node tests alone do not validate layout. See `docs/dashboard.md`.
- Test installs and upgrades in disposable HA, not by restarting or modifying a
  user's live installation without authorization. Restart HA and hard-refresh
  the browser when checking updated bundled assets.

## Security and public artifacts

Never commit live HA tokens, DeviceAuth values, guide/player bearer URLs, or
private configuration. Use synthetic data in fixtures, diagnostics examples,
and screenshots. Diagnostic redaction must cover raw datagrams and numeric
protocol tags as well as named fields. Removing a value from the working tree
does not revoke it or remove historical exposure. Preserve upstream notices;
do not infer a license from HA, HACS, or another repository by the same author.

## Git and pull requests

- `main` is stable/default, `develop` is fork development, and `uvjim` preserves
  upstream-only history. `origin` is this fork; `upstream` is uvjim's repository.
  Never merge fork changes into `uvjim` or reset fork branches to upstream.
- Use a separate worktree for implementation. Preserve unrelated working changes.
- Use Conventional Commit subjects describing the change, not provisional
  release versions. Keep useful intent, decisions, and constraints in the body.
  Do not rewrite published history to clean up old subjects without permission.
- Prefer pull requests. Push and merge only with authorization. After an
  authorized merge into `develop`, fast-forward its primary checkout without
  overwriting unrelated work.

## CI and release gates

`validate.yml` runs Python tests/Ruff, dashboard tests, and Hassfest.
`hacs.yml` independently runs full HACS eligibility without ignored checks.
Both run automatically on pushes to and PRs targeting `main` or `develop`, plus
daily schedules. Use automatic runs; do not manually dispatch duplicates.

After an authorized push or PR update, inspect both workflows for the exact
head SHA. Subscribe to their results separately and to PR comments/reviews when
supported. Missing, skipped, cancelled, or older-head runs are not passing CI.
Before an authorized merge, check all current PR checks, not just the Validate
badge. That badge reports code validation; **HACS: Custom** is an installation
channel label, not eligibility certification.

`main.yml` runs on version tags and requires Validate before packaging.
The manifest must match the tag (`year.month.revision`, optional `bN`, no `v`),
the commit must be on `main`, and curated `docs/releases/<tag>.md` must exist.
The ZIP contains runtime files at its root and the root license if present.
Release bodies use curated notes, not generated commit titles.
Finalize candidate wording and release-page links before tagging.

Inherited-code licensing remains unresolved; do not add a blanket license or
ignore that HACS failure. The owner has chosen versioned custom-install releases
independently of HACS default-list eligibility; this does not resolve licensing.
Release preparation is not authorization to tag,
publish, submit to HACS, or deploy. The workflow creates drafts only; publication
requires separate authorization. See `docs/releasing.md` for provenance,
licensing research, release checks, and default HACS submission requirements.
