#!/bin/zsh
# Test, commit, build and replace /Applications/Foldset.app, stopping at the first failure.
# Usage: zsh scripts/ship.sh "commit message"   (message is required only when there are changes)
set -eu
cd "${0:A:h}/.."
TARGET=/Applications/Foldset.app
BUNDLE_ID=com.xuxia.foldertemplates
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
# Backups go to the main checkout so they survive worktree cleanup.
MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"

if [[ -n "$(git status --porcelain)" && $# -eq 0 ]]; then
    echo "There are uncommitted changes; pass a commit message." >&2; exit 1
fi

echo "== 1/4 Test"
zsh scripts/test.sh

echo "== 2/4 Commit"
if [[ -n "$(git status --porcelain)" ]]; then
    git add -A
    git commit -m "$1"
else
    echo "Nothing to commit; installing $(git rev-parse --short HEAD)."
fi

echo "== 3/4 Build"
zsh scripts/build.sh

echo "== 4/4 Install"
was_running=0
icon_changed=1
[[ -f "$TARGET/Contents/Resources/Assets.car" ]] && cmp -s "$TARGET/Contents/Resources/Assets.car" output/Foldset.app/Contents/Resources/Assets.car && icon_changed=0
if pgrep -f "$TARGET/Contents/MacOS/" >/dev/null; then
    was_running=1
    osascript -e "quit app id \"$BUNDLE_ID\""
    for _ in {1..20}; do pgrep -f "$TARGET/Contents/MacOS/" >/dev/null || break; sleep 0.5; done
    if pgrep -f "$TARGET/Contents/MacOS/" >/dev/null; then echo "Foldset did not quit; install aborted." >&2; exit 1; fi
fi
if [[ -d "$TARGET" ]]; then
    BACKUP="$MAIN/output/Backups/App-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP"
    ditto "$TARGET" "$BACKUP/Foldset.app"
    # Keep the old copy out of LaunchServices so it cannot supply the app's icon.
    "$LSREGISTER" -u "$BACKUP/Foldset.app" 2>/dev/null || true
    echo "Backup: $BACKUP/Foldset.app"
    rm -rf "$TARGET"
fi
ditto output/Foldset.app "$TARGET"
codesign --verify --deep --strict "$TARGET"
"$LSREGISTER" -f "$TARGET"
touch "$TARGET"
# The Dock caches icons per bundle ID and ignores a changed Assets.car until its cache is rebuilt.
if (( icon_changed )); then
    rm -f "$(getconf DARWIN_USER_CACHE_DIR)com.apple.dock.iconcache"
    killall Dock
fi
if (( was_running )); then
    # LaunchServices can briefly refuse (-600) right after the old process exits.
    for _ in {1..5}; do open "$TARGET" 2>/dev/null && break; sleep 1; done
fi
echo "Installed $(git rev-parse --short HEAD) to $TARGET"
