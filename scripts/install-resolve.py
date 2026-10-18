# -*- coding: utf-8 -*-
"""Install only Foldset's own Resolve menu scripts, preserving prior versions."""
from pathlib import Path
import shutil
from datetime import datetime
root = Path(__file__).resolve().parents[1]
support = Path.home() / 'Library/Application Support/Foldset/Resolve'
menu = Path.home() / 'Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/Foldset'
backup = root / 'output/Backups' / ('Resolve-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
for path in (support, menu):
    path.mkdir(parents=True, exist_ok=True)

def write(path, data):
    if path.exists():
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup / path.name)
    path.write_text(data, encoding='utf-8')

for name in ('foldset_bins.py', 'foldset_resolve.py', 'foldset_usage.py', 'foldset_tags.py', 'foldset_usage_ui.py', 'foldset_moves.py', 'foldset_browser.py', 'foldset_trash.py', 'foldset_dialogs.py', 'foldset_pool_cleanup.py'):
    write(support / name, (root / 'Integrations/DaVinciResolve' / name).read_text(encoding='utf-8'))
import subprocess
subprocess.run(['xcrun','swiftc',str(root / 'Integrations/DaVinciResolve/TrashFile.swift'),'-o',str(support / 'FoldsetTrashFile')],check=True)
import sys
sys.path.insert(0, str(root / 'Integrations/DaVinciResolve'))
from foldset_bins import load_library
from foldset_menu import sync_menu
# Retire only the two explicitly identified legacy entry points; preserve them.
for name in ('使用默认模板创建媒体夹.py', '选择模板创建媒体夹.py'):
    old = menu / name
    if old.exists():
        backup.mkdir(parents=True, exist_ok=True)
        old.rename(backup / name)
sync_menu(load_library(), menu, backup)
print(menu)

write(menu / 'Finder 使用状态标记.py', (root / 'Integrations/DaVinciResolve/Finder 使用状态标记.py').read_text(encoding='utf-8'))
