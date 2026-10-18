#!/bin/zsh
set -eu
cd "${0:A:h}/.."
APP="$PWD/output/Foldset.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -swift-version 5 -O -target arm64-apple-macosx14.0 Sources/Core.swift Sources/Store.swift Sources/ResolveExtension.swift Sources/ResolveExtensionView.swift Sources/Theme.swift Sources/NativeSettingsView.swift Sources/App.swift -o "$APP/Contents/MacOS/XuXia" -framework SwiftUI -framework AppKit
cp Assets/Info.plist "$APP/Contents/Info.plist"
cp Design/FunEditStudio/Foldset-AppIcon/Assets.car Design/FunEditStudio/Foldset-AppIcon/Foldset.icns "$APP/Contents/Resources/"
cp Design/FunEditStudio/BrandIcon-transparent.png "$APP/Contents/Resources/BrandIcon.png"
zsh scripts/bundle-resolve.sh "$APP"
codesign --force --sign - "$APP"
echo "Built: $APP"
