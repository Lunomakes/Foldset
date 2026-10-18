# -*- coding: utf-8 -*-
"""Generate one Resolve menu entry per immutable template ID."""
import json
import unicodedata
from pathlib import Path
from datetime import datetime
MARKER = '# Foldset managed preset'

def sync_menu(library, menu, archive):
    menu.mkdir(parents=True, exist_ok=True)
    desired = {}
    for index, template in enumerate(library['templates']):
        name = ''.join('_' if c in '/:' or unicodedata.category(c).startswith('C') else c
                       for c in template['name'].strip())[:60] or '未命名模板'
        filename = '%02d %s.py' % (index + 1, name)
        desired[filename] = '''# -*- coding: utf-8 -*-
# Foldset managed preset
import sys
from pathlib import Path
support = str(Path.home() / 'Library/Application Support/Foldset/Resolve')
if support not in sys.path:
    sys.path.insert(0, support)
import importlib
import foldset_bins
import foldset_resolve
importlib.reload(foldset_bins)
importlib.reload(foldset_resolve)
foldset_resolve.main(resolve, bmd, template_id=%s)
''' % json.dumps(template['id'])
    for path in menu.glob('*.py'):
        if MARKER in path.read_text(encoding='utf-8') and path.name not in desired:
            archive.mkdir(parents=True, exist_ok=True)
            path.rename(archive / (datetime.now().strftime('%Y%m%d%H%M%S%f-') + path.name))
    for filename, content in desired.items():
        path = menu / filename
        if path.exists() and MARKER not in path.read_text(encoding='utf-8'):
            raise ValueError('菜单中存在非 Foldset 文件：' + filename)
        path.write_text(content, encoding='utf-8')
