# Amp pull request validation

Amp-created pull requests are the primary contribution path for this repository.
Automatic `push` and `pull_request` validation has not reliably started for Amp
changes, while explicit `workflow_dispatch` runs have worked. Do not rely on an
automatic event or a commit-status rollup to start or discover validation.

## After opening or updating a pull request

When the user has authorized pushing a branch or opening a PR, run the
non-deploying `Validate` workflow as part of that work:

1. Read the PR's current head branch and full head SHA from GitHub. Confirm the
   head repository is `rtgibbons/hass_hdhomerun`; do not dispatch a different
   repository's branch with the same name.
2. Explicitly dispatch `validate.yml` on that head branch:
   `gh workflow run validate.yml --repo rtgibbons/hass_hdhomerun --ref <head-branch>`.
   Do this for the initial PR and every subsequent pushed head, not only after a
   missing-check notification. This starts validation, not Build & Release.
3. Inspect the returned workflow run and verify its `headSha` equals the PR's
   current head SHA. If the branch changed, validation of the older commit does
   not cover the new head.
4. Subscribe this thread to CI for the exact head SHA with
   `workflow_file: "validate.yml"`, in addition to the usual PR comments/reviews
   subscription. Prefer workflow-specific monitoring: commit rollups have
   reported no checks even while explicitly dispatched Validate runs were active.
5. Report the run link and handle failures. A missing run, empty check list,
   skipped/cancelled job, or successful local test run is not passing GitHub CI.

## Before merging

Merge only when the user has authorized it. Re-read the PR head and verify a
completed, successful Validate run for that exact SHA, including successful
`Tests and Ruff` and `Hassfest` jobs. Check any other reported PR checks too; a
successful Validate run does not override a failure elsewhere.

After an authorized merge, fast-forward the primary checkout's `develop` to
`origin/develop` without overwriting anyone else's changes. Keep the existing
automatic workflow triggers for non-Amp contributions; explicit dispatch is the
primary Amp path, not a claim that GitHub's missing event triggers were repaired.
