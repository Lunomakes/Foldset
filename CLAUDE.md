# Foldset

- After finishing a change to the app, run `zsh scripts/ship.sh "<commit message>"`. It tests, commits, builds and replaces /Applications/Foldset.app, stopping at the first failure. End the message with the commit attribution trailer. Report the test result, commit hash and backup path.
- If tests fail, fix the cause and rerun; do not commit or install around a failure.
