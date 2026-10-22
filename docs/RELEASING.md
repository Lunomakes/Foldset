# Releasing Foldset

Foldset ships as GitHub Releases on `Lunomakes/Foldset`. The in-app updater follows
`https://github.com/Lunomakes/Foldset/releases/latest`, downloads
`Foldset-<version>-arm64.zip`, checks it against `Foldset-<version>-arm64.zip.sha256`, and
only offers versions newer than the running one.

## CI

`.github/workflows/ci.yml` runs `zsh scripts/ci.sh` on a `macos-26` runner for every push
to `main`, every pull request, and on demand. The script runs, in order:

1. `scripts/test.sh` — Swift core tests
2. each `Tests/*Tests.py` on its own (`unittest discover` cannot import some of them)
3. `scripts/package.sh` — build, ad-hoc sign, zip + dmg + `.sha256`
4. `scripts/test-resolve-extension.sh` — DaVinci Resolve extension tests against the built app

The zip/dmg land in the run's `Foldset-<sha>` artifact (kept 14 days). CI builds are a
check, not the shipped binary: releases are still built and uploaded from the maintainer's Mac.

Run the same checks locally with `zsh scripts/ci.sh`.

## Release

1. Bump `CFBundleShortVersionString` (and `CFBundleVersion`) in `Assets/Info.plist`, commit, and
   make sure CI is green on that commit.
2. `zsh scripts/package.sh` → `output/Release/Foldset-<version>-arm64.{zip,dmg}` plus `.sha256`.
3. **Pre-release (staging).** Publish as a prerelease; `releases/latest` skips prereleases, so
   no installed copy is offered it yet:

   ```bash
   gh release create v<version> output/Release/Foldset-<version>-arm64.* --prerelease --title "Foldset <version>" --notes "..."
   ```

   Verify: download the zip from the release page, check `shasum -a 256 -c`, open the app, and
   on an older installed build confirm "Check for Updates" still reports the previous version.
4. **Promote (production).** `gh release edit v<version> --prerelease=false --latest`, then
   confirm `curl -sI https://github.com/Lunomakes/Foldset/releases/latest` redirects to
   `/tag/v<version>` and that an older build now offers the update and installs it.

## Rollback

- **Stop the rollout:** `gh release edit v<version> --prerelease` (or delete the release).
  `releases/latest` falls back to the previous release, so no new installs pick up the bad one.
- **Users already on the bad version** stay there: the updater never downgrades. Fix forward
  with a higher patch version, or have them install the previous zip/dmg from the releases page.
- **Local install** (`scripts/ship.sh`): the replaced app is kept at
  `output/Backups/App-<timestamp>/Foldset.app` in the main checkout; copy it back to
  `/Applications/Foldset.app`.
