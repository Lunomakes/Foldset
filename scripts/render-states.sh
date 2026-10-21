#!/bin/zsh
# Render every SwiftUI UI state to PNG for review. Writes only into the given directory.
# Windows appear on screen briefly while they are captured (needs Screen Recording permission).
set -eu
cd "${0:A:h}/.."
OUT="${1:?usage: render-states.sh <output-dir>}"
mkdir -p "$OUT"
swiftc -swift-version 5 -parse-as-library -D RENDER_STATES -target arm64-apple-macosx14.0 \
    Sources/Core.swift Sources/Store.swift Sources/ResolveExtension.swift Sources/ResolveExtensionView.swift \
    Sources/Updater.swift Sources/Theme.swift Sources/NativeSettingsView.swift Sources/App.swift Tests/RenderStates.swift \
    -o "$OUT/RenderStates" -framework SwiftUI -framework AppKit
# Bare executables look up resources next to themselves.
cp Design/FunEditStudio/BrandIcon-transparent.png "$OUT/BrandIcon.png"
"$OUT/RenderStates" "$OUT"
