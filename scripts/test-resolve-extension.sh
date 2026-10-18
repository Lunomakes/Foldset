#!/bin/zsh
# Tests use isolated output directories and never connect to a live Resolve instance.
set -eu
cd "${0:A:h}/.."
PAYLOAD="$PWD/output/Foldset.app/Contents/Resources/ResolveExtension"
if [[ ! -f "$PAYLOAD/manifest.json" ]]; then
    print -u2 'Build first: zsh scripts/build.sh'
    exit 1
fi
swiftc -swift-version 5 Sources/Core.swift Sources/Store.swift Sources/ResolveExtension.swift Tests/ResolveExtensionTests.swift -o output/ResolveExtensionTests -framework SwiftUI -framework AppKit
output/ResolveExtensionTests "$PAYLOAD"
