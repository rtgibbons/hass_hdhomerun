# Release and HACS submission checklist

[Documentation index](README.md)

This guide covers releases of this fork and submission to HACS's default list.
A draft GitHub release does not satisfy the default-listing release requirement.

## Release policy

**2026.10.1 is the first fork release for custom installation.** The latest upstream
release verified on October 25, 2026 was
[2026.9.1](https://github.com/uvjim/hass_hdhomerun/releases/tag/2026.9.1).
The fork follows upstream's `year.month.revision` versioning, with its own
release sequence. HACS tracks releases per repository; an upstream release with
the same version does not conflict with this fork's release. Optional beta tags
use `year.month.revisionbN`, such as `2026.10.1b1`, and must exactly match the
source manifest. Keep future fork versions increasing.

The owner has chosen versioned custom-install snapshots while licensing remains
unresolved. Code validation gates packaging; HACS default-list eligibility is
checked independently and is not a custom-release gate. This is not a license
grant or a claim that permissions have been resolved. See the
[release notes](releases/2026.10.1.md).

## Release review and default-list requirements

- Establish redistribution/license permissions for upstream code and vendored
  dependencies. Preserve existing notices. If no license grant can be found,
  contact the copyright owner rather than choosing a license on their behalf.
  Default HACS inclusion requires a GitHub-recognized, OSI-approved license.
- Review a redacted secret scan of the release tree and all reachable Git
  history. Check screenshots and diagnostics manually too. If a real secret was
  published, revoke/rotate it; deleting its current file does not revoke it or
  remove it from history. Coordinate any history rewrite separately.
- Keep this fork clearly credited to its upstream origin. The shared
  `hdhomerun` domain intentionally preserves compatibility; users must not
  install upstream and this fork side-by-side.
- Confirm any same-domain/default-listing questions with HACS reviewers before
  assuming a second listing will be accepted. Custom-repository installation
  and default-list inclusion are different things.

### Licensing status

As of October 25, 2026, no explicit license grant has been found for the
inherited integration in `uvjim/hass_hdhomerun`. Review of its 274 reachable
commits, current branches/tags, issue/PR descriptions, and 152 issue/PR comments
did not establish permission to release the inherited code under an open-source
license. Neither did review of all 40 public release descriptions and eight
attached integration ZIPs. This does not rule out a private agreement or
unavailable evidence, including forum content that could not be fully retrieved.

The bundled `pyhdhr` implementation was introduced within the integration in
[the April 2022 rewrite](https://github.com/uvjim/hass_hdhomerun/commit/b376809b1728d66ea066c283c3958a3935cf4747).
Its protocol module explicitly references SiliconDust's `libhdhomerun`, whose
[protocol header carries LGPL-2.1-or-later terms](https://github.com/Silicondust/libhdhomerun/blob/b0e5d5f5c8e2bf37dea34beb014e08ebb598ebf6/hdhomerun_pkt.h#L4-L9).
That establishes a reference source, not an LGPL grant for the Python
implementation or the entire integration. Clarify whether any licensed source
was adapted and preserve any applicable notices; similarly named Python packages
do not establish this code's license.

There is no automatic Home Assistant or HACS fallback license:

- [Home Assistant's licensing guidance](https://contributors.home-assistant.io/start/licensing/)
  applies to contributions to its projects; a custom integration does not become
  Apache-2.0 simply by running in Home Assistant.
- [HACS default inclusion](https://www.hacs.xyz/docs/publish/include/#check-license)
  requires an identifiable, OSI-approved license; it does not grant one.
- [GitHub's terms, sections D.5–D.6](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content)
  allow public repositories to be viewed and forked through GitHub. Contributions
  inherit a repository license when a license notice exists; these terms do not
  supply a missing open-source license.

For resolution, obtain a written grant covering the inherited code and relevant
contributions, and check vendored code separately. Apache-2.0 is a reasonable
license to request, not one this fork can assign to others' code without
authorization. Attribution and an unanswered permission request do not resolve
the licensing question or the default-list blocker.

## Repository metadata

The repository must be public, not archived, and have a description, topics,
and Issues enabled. Suggested metadata for this fork:

- Description: **HDHomeRun for Home Assistant — maintained fork with a bundled
  dashboard, tuner diagnostics, and XMLTV/M3U guide proxy.**
- Topics: `home-assistant`, `hacs`, `hdhomerun`, `xmltv`, `iptv`.
- Default branch: `main`, the stable fork branch.
- Support: this fork's issue tracker, not upstream's.

### Branch responsibilities

- `uvjim`: preserved upstream-only history, updated manually from
  `uvjim/hass_hdhomerun`'s `main`. Never merge fork changes into this branch.
- `main`: stable/default fork branch and the source of release commits. It can
  be selected for custom-install testing before the first published release.
- `develop`: ongoing integration work, available only as an opt-in development
  installation. Integrate tested fork work into `main` before release.

After publication, normal HACS installations use published release tags, not
the moving `main` or `develop` branches. Keeping an upstream-history branch does
not make upstream releases releases of this fork.

The `upstream` Git remote points to `https://github.com/uvjim/hass_hdhomerun.git`;
`origin` points to this fork. To refresh only the preserved upstream branch:

```bash
git fetch upstream main
git push origin upstream/main:uvjim
```

This uses a normal fast-forward push, never a force push. Review and merge
upstream updates into `develop` separately, validate them, then promote tested
fork changes to `main`. Do not reset either fork branch to upstream.

## Validate the exact release candidate

1. Prepare `2026.10.1` in `custom_components/hdhomerun/manifest.json` in source.
   For later releases, choose the next calendar version. The version must be
   committed on `main` before any matching tag is authorized. Do not retain an
   upstream version for the fork's first release.
2. Run Python tests, Ruff, dashboard tests, Markdown lint, workflow lint,
   Hassfest, and a fresh secret scan. Validate packaged frontend assets and
   translations, not only Python files.
3. Push the candidate branch and verify the automatic `validate.yml` and
   `hacs.yml` runs, following the repository's `AGENTS.md` instructions.
4. Verify successful **Tests and Ruff**, dashboard tests, and **Hassfest** in
   **Validate** for the exact candidate commit. Inspect **HACS eligibility**
   separately and report failures without ignores. It must pass before default
   HACS submission, but does not gate custom releases. Local checks do not
   replace these GitHub results.
5. Verify installation/update in a disposable HA instance, including a hard
   browser refresh, dashboard addition, and preservation of existing entities.
   Do not use production maintenance actions for validation.

The intended **Validate** contract covers pushes and pull requests targeting
both `main` and `develop`, supports manual dispatch, and is reusable by the
release workflow. Use automatic runs and verify the exact head SHA as required
by `AGENTS.md`; do not dispatch duplicate runs after each push.

**HACS eligibility** has the same triggers and is separately reusable. Its
listing-readiness result does not affect the Validate badge. The static
**HACS: Custom** badge describes installation, not a passing eligibility check.

## Prepare the release

The repository uses `zip_release: true` and `filename: "hdhomerun.zip"`: HACS
downloads the attached release asset. The same ZIP supports manual installation.
Its manifest and runtime files must match the tagged source exactly.

The release workflow's required contract is:

- Accept numeric `x.y.z` and `x.y.zbN` tags, with no calendar-month restriction.
- Verify that the tagged source manifest equals the tag exactly and that the
  tagged commit is on `main`; do not rewrite the manifest only inside the ZIP.
- Run reusable **Validate** successfully before building. A failure or skipped
  validation must prevent packaging. Keep **HACS eligibility** independent.
- Package integration files at the root of `hdhomerun.zip`, excluding portal
  metadata, Python bytecode, and cache files. Include the root license in the
  ZIP if present and preserve any additional required third-party notices.
- Create a **draft only**, marking beta releases as prereleases. Publication is
  a separate, explicitly authorized decision after all gates pass.
- Require `docs/releases/<tag>.md` and use it as the draft release body instead
  of generating notes from commit or pull-request titles. Before tagging,
  finalize its unreleased wording and use links that work on GitHub releases.

Confirm these workflow gates on the final candidate; documenting the contract
does not establish that they have run or passed. Do not push a tag just to test
the workflow: that creates shared release state. Tags and publication require
explicit authorization.

Before publication, review release notes for minimum HA version,
fork attribution, dashboard setup, optional EPG behavior, breaking changes, and
upgrade/rollback instructions. Verify both the tagged source and ZIP contents.
Publish an authorized custom release only after code validation and ZIP checks
pass. A draft is not downloadable through normal HACS release installation;
publish it with its ZIP asset before directing users to that version.

## Submit for default HACS inclusion

Follow the current
[general publishing requirements](https://www.hacs.xyz/docs/publish/start/),
[integration requirements](https://www.hacs.xyz/docs/publish/integration/), and
[default inclusion process](https://www.hacs.xyz/docs/publish/include/).

The owner or a major contributor submits a separate branch/PR to
[`hacs/default`](https://github.com/hacs/default), adding the repository to the
alphabetically sorted integration list. Complete the submission template
accurately and keep the PR editable. A new repository needs a published release
and passing HACS/Hassfest validation before submission.

The `hdhomerun` custom-integration brand already exists in
[`home-assistant/brands`](https://github.com/home-assistant/brands/tree/master/custom_integrations/hdhomerun).
Do not create a duplicate brand merely because this fork's display name differs.
If changing the internal domain in the future, treat it as an explicit migration
and recheck both core-domain conflicts and branding requirements.
