#!/bin/zsh
set -eu
cd "${0:A:h}/.."
APP="$PWD/output/Foldset Preview.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$PWD/output/NativePreviewData"
if [[ ! -f "$PWD/output/NativePreviewData/templates.json" && -f "$HOME/Library/Application Support/XuXia/templates.json" ]]; then
    cp "$HOME/Library/Application Support/XuXia/templates.json" "$PWD/output/NativePreviewData/templates.json"
fi
swiftc -swift-version 5 -D NATIVE_PREVIEW -O -target arm64-apple-macosx14.0 Sources/Core.swift Sources/Store.swift Sources/ResolveExtension.swift Sources/ResolveExtensionView.swift Sources/Theme.swift Sources/NativeSettingsView.swift Sources/App.swift -o "$APP/Contents/MacOS/XuXia" -framework SwiftUI -framework AppKit
cp Assets/Info.plist "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier com.xuxia.foldertemplates.nativepreview' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleName Foldset Preview' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleDisplayName Foldset Preview' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Delete :NSServices' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :PreviewLibraryPath string $PWD/output/NativePreviewData/templates.json" "$APP/Contents/Info.plist"
cp Design/FunEditStudio/Foldset-AppIcon/Assets.car Design/FunEditStudio/Foldset-AppIcon/Foldset.icns "$APP/Contents/Resources/"
cp Design/FunEditStudio/BrandIcon-transparent.png "$APP/Contents/Resources/BrandIcon.png"
zsh scripts/bundle-resolve.sh "$APP"
codesign --force --sign - "$APP"
echo "Built: $APP"
