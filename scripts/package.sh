#!/bin/zsh
# Build Foldset and package it for a GitHub release as a zip and a drag-to-Applications dmg, plus SHA-256 files.
# Usage: zsh scripts/package.sh   -> output/Release/Foldset-<version>-arm64.{zip,dmg}
set -eu
cd "${0:A:h}/.."
zsh scripts/build.sh
APP=output/Foldset.app
VERSION="$(plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")"
NAME="Foldset-$VERSION-arm64"
OUT=output/Release
mkdir -p "$OUT"
rm -f "$OUT/$NAME.zip" "$OUT/$NAME.dmg" "$OUT/$NAME".*.sha256(N)

ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/$NAME.zip"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/Foldset.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "Foldset $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO "$OUT/$NAME.dmg"

cd "$OUT"
for f in "$NAME.zip" "$NAME.dmg"; do shasum -a 256 "$f" > "$f.sha256"; done
cat "$NAME".*.sha256
ls -lh "$NAME.zip" "$NAME.dmg"
