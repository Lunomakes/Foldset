#!/bin/zsh
# Build-time only. End users never need a compiler or a terminal.
set -eu
APP="$1"
PAYLOAD="$APP/Contents/Resources/ResolveExtension"
mkdir -p "$PAYLOAD"
for name in foldset_bins foldset_resolve foldset_usage foldset_tags foldset_usage_ui foldset_moves foldset_browser foldset_trash foldset_dialogs foldset_pool_cleanup; do
    cp "Integrations/DaVinciResolve/$name.py" "$PAYLOAD/$name.py"
done
cp 'Integrations/DaVinciResolve/Finder 使用状态标记.py' "$PAYLOAD/"
swiftc -swift-version 5 -O -target arm64-apple-macosx14.0 Integrations/DaVinciResolve/TrashFile.swift -o "$PAYLOAD/FoldsetTrashFile"
codesign --force --sign - "$PAYLOAD/FoldsetTrashFile"
python3 - "$PAYLOAD" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
names = ['foldset_' + n + '.py' for n in ('bins', 'resolve', 'usage', 'tags', 'usage_ui', 'moves', 'browser', 'trash', 'dialogs', 'pool_cleanup')]
names += ['FoldsetTrashFile', 'Finder 使用状态标记.py']
manifest = {'version': '1.0.0', 'files': {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}}
(root/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
PY
