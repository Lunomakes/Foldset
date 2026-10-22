#!/bin/zsh
# Everything CI checks, runnable locally: tests, release packaging, then the Resolve extension tests on the packaged app.
# Usage: zsh scripts/ci.sh   -> output/Release/Foldset-<version>-arm64.{zip,dmg}
set -eu
cd "${0:A:h}/.."

echo "== Swift core tests"
zsh scripts/test.sh

echo "== Python tests"
# Run each file on its own: some modules under test parse sys.argv at import, which breaks `unittest discover`.
for f in Tests/*Tests.py; do
    echo "-- $f"
    python3 "$f"
done

echo "== Build and package"
zsh scripts/package.sh

echo "== Resolve extension tests"
zsh scripts/test-resolve-extension.sh
