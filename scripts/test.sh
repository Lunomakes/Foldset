#!/bin/zsh
set -eu
cd "${0:A:h}/.."
mkdir -p output
swiftc -swift-version 5 Sources/Core.swift Sources/Store.swift Tests/CoreTests.swift -o output/CoreTests -framework SwiftUI -framework AppKit
RESULTS=$(mktemp -d "$PWD/output/TestResults-XXXXXX")
output/CoreTests "$RESULTS"
echo "Test artifacts retained: $RESULTS"
