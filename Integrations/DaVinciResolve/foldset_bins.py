# -*- coding: utf-8 -*-
"""Shared, non-destructive Foldset media-bin operations."""
import json
import unicodedata
from pathlib import Path


def key(name):
    return unicodedata.normalize('NFC', name).lower()


def load_library(path=None):
    path = path or Path.home() / 'Library/Application Support/XuXia/templates.json'
    with open(path, encoding='utf-8') as source:
        library = json.load(source)
    if not isinstance(library.get('templates'), list) or not library['templates']:
        raise ValueError('请先在 Foldset 中保存至少一套模板。')
    return library


def names_for(template):
    if not template['name'].strip():
        raise ValueError('请先为模板命名。')
    entries = template['entries']
    start = template.get('start', 1)
    if not entries or len(entries) > 1000 or not 0 <= start <= 999999:
        raise ValueError('请检查模板的条目数量和起始序号。')
    digits = max(0, min(6, template.get('digits', 2)))
    names, seen = [], set()
    for index, entry in enumerate(entries):
        raw = entry['name'].strip()
        name = (str(start + index).zfill(digits) + template.get('separator', '_') + raw
                if template.get('numbered', True) else raw)
        if (not raw or raw in ('.', '..') or name.startswith('.') or '/' in name
                or ':' in name or any(unicodedata.category(c) in ('Cc', 'Cf') for c in name)
                or len(name.encode('utf-8')) > 255):
            raise ValueError('第 %d 个名称无效，请在 Foldset 中修改。' % (index + 1))
        if key(name) in seen:
            raise ValueError('模板中存在重复名称：' + name)
        seen.add(key(name))
        names.append(name)
    return names


def create_bins(pool, parent, names):
    """Capture a parent before calling. Never delete, rename, or move existing bins."""
    if not pool or not parent:
        raise ValueError('请打开项目并选中一个普通媒体夹。')
    if not names or len({key(n) for n in names}) != len(names):
        raise ValueError('媒体夹名称为空或重复。')
    children = parent.GetSubFolderList()
    if children is None:
        raise ValueError('无法读取目标媒体夹，请重新选择普通媒体夹。')
    existing = {key(child.GetName()) for child in children}
    created, skipped = [], []
    try:
        for name in names:
            if key(name) in existing:
                skipped.append(name)
                continue
            if not pool.AddSubFolder(parent, name):
                raise RuntimeError('创建“%s”失败；本次已创建 %d 个，跳过 %d 个。已创建内容保留。'
                                   % (name, len(created), len(skipped)))
            existing.add(key(name))
            created.append(name)
    finally:
        # AddSubFolder makes each new bin current, which leaves the user inside the last one
        # with the bin tree collapsed. Return to the bin they started from.
        if created:
            pool.SetCurrentFolder(parent)
    return {'created': created, 'skipped': skipped}
