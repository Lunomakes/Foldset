# -*- coding: utf-8 -*-
# Foldset utility launcher (not a generated preset)
import sys
from pathlib import Path
support = str(Path.home() / 'Library/Application Support/Foldset/Resolve')
if support not in sys.path:
    sys.path.insert(0, support)
# Refresh the small filesystem backend even when reusing an existing window.
# Execute UTF-8 source directly so cached bytecode cannot retain an old decoder.
import foldset_trash
exec(compile(Path(support, 'foldset_trash.py').read_text(encoding='utf-8'), str(Path(support, 'foldset_trash.py')), 'exec'), foldset_trash.__dict__)
# Check the host registry before importing/reloading modules: another script
# context may already own the active window and its scan/undo state.
existing = resolve.Fusion().UIManager.FindWindow("FoldsetFinderUsage")
if existing:
    existing.Show()
    existing.Raise()
    existing.ActivateWindow()
else:
    # Load installed UTF-8 source rather than stale module/bytecode state.
    import importlib
    for name in ('foldset_usage', 'foldset_tags', 'foldset_moves',
                 'foldset_pool_cleanup', 'foldset_dialogs', 'foldset_trash',
                 'foldset_browser', 'foldset_usage_ui'):
        module = importlib.import_module(name)
        path = Path(support, name + '.py')
        module.__file__ = str(path)
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
    import foldset_usage_ui
    foldset_usage_ui.open_window(resolve, bmd)
