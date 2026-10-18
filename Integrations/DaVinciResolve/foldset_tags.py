# -*- coding: utf-8 -*-
"""Finder tags, with per-file journals and non-destructive undo."""
import csv
import ctypes
import errno
import json
import os
import plistlib
import uuid
from datetime import datetime
from pathlib import Path
from foldset_usage import file_key

ATTR = 'com.apple.metadata:_kMDItemUserTags'
_LIBC = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
_LIBC.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
_LIBC.getxattr.restype = ctypes.c_ssize_t
_LIBC.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
_LIBC.setxattr.restype = ctypes.c_int
_LIBC.removexattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
_LIBC.removexattr.restype = ctypes.c_int
_MISSING = (getattr(errno, 'ENOATTR', 93), errno.ENODATA)

def _raise_errno(path):
    code = ctypes.get_errno()
    raise OSError(code, os.strerror(code), path)

def get_attribute(path):
    args = (os.fsencode(path), ATTR.encode())
    size = _LIBC.getxattr(*args, None, 0, 0, 0)
    if size < 0:
        _raise_errno(path)
    buffer = ctypes.create_string_buffer(size)
    count = _LIBC.getxattr(*args, buffer, size, 0, 0)
    if count < 0:
        _raise_errno(path)
    return buffer.raw[:count]

def set_attribute(path, data):
    buffer = ctypes.create_string_buffer(data)
    if _LIBC.setxattr(os.fsencode(path), ATTR.encode(), buffer, len(data), 0, 0) < 0:
        _raise_errno(path)

def remove_attribute(path):
    if _LIBC.removexattr(os.fsencode(path), ATTR.encode(), 0) < 0:
        code = ctypes.get_errno()
        if code not in _MISSING:
            raise OSError(code, os.strerror(code), path)

LABELS = {'used': ('已使用', 2), 'unused': ('未使用候选', 1), 'unknown': ('待核实', 5), 'not_imported': ('未导入当前项目', 4)}
ROOT = Path.home() / 'Library/Application Support/Foldset/Resolve/UsageReports'


def read_tags(path):
    try:
        raw = get_attribute(path)
    except OSError as error:
        if error.errno in _MISSING:
            return []
        raise
    tags = plistlib.loads(raw)
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError('现有 Finder 标签格式异常，未覆盖。')
    return tags


def write_tags(path, tags):
    # No tags left: remove the attribute instead of leaving an empty list, as Finder does.
    if tags:
        set_attribute(path, plistlib.dumps(tags, fmt=plistlib.FMT_BINARY))
    else:
        remove_attribute(path)
    if read_tags(path) != tags:
        raise OSError('Finder 标签写入后校验不一致。')


def save_json(path, data):
    path = Path(path)
    temporary = path.with_suffix('.pending')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def namespace(report):
    # Stable project-scoped labels prevent one project from erasing another's tags.
    return 'Foldset·' + report['projectID'] + '·'


def tag_for(report, status):
    title, color = LABELS[status]
    scope = '全部时间线' if report['scope'] == 'all' else '当前时间线'
    return namespace(report) + scope + '·' + title + '\n' + str(color)


def prepare_report(report, root=ROOT):
    folder = Path(root) / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    save_json(folder / 'scan.json', report)
    with (folder / '文件清单.csv').open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(['状态','源文件','范围','扫描时间'])
        for record in report['records']:
            writer.writerow([LABELS[record['status']][0],record['path'],report['scope'],report['scannedAt']])
    return folder


def apply(report, folder):
    folder = Path(folder)
    journal = {'project':report['project'], 'prefix':namespace(report), 'entries':[]}
    location = folder / 'tag-journal.json'
    save_json(location, journal)
    for record in report['records']:
        entry = {'path':record['path'], 'identity':record['identity'], 'state':'failed'}
        journal['entries'].append(entry)
        try:
            if file_key(record['path']) != record['identity']:
                raise ValueError('源文件已被替换或离线，跳过。')
            before = read_tags(record['path'])
            desired = [t for t in before if not t.startswith(journal['prefix'])] + [tag_for(report,record['status'])]
            entry.update(before=before, after=desired, state='prepared')
            save_json(location, journal)  # Persist restoration data before any metadata write.
            if read_tags(record['path']) != before:
                raise ValueError('标签被其他程序修改，请重新扫描。')
            write_tags(record['path'], desired)
            entry['state'] = 'applied'
        except Exception as error:
            entry['error'] = str(error)
        save_json(location, journal)
    successful = [e for e in journal['entries'] if e['state'] == 'applied']
    if successful:
        # Exact project/scope tag: Finder's Spotlight query does not match generic gray tags.
        scopes = sorted({str(Path(e['path']).parent) for e in successful})
        for status, title in (('unused', '未使用候选'), ('not_imported', '未导入当前项目')):
            tag = tag_for(report, status).split('\n')[0]
            escaped = tag.replace('\\','\\\\').replace('"','\\"')
            search = {'RawQuery':'kMDItemUserTags == "%s"' % escaped,
                      'SearchCriteria':{'FXScopeArrayOfPaths':scopes, 'CurrentFolderPath':'/',
                                        'FXScope':0, 'FXCriteriaSlices':[]}}
            (folder / (title + '.savedSearch')).write_bytes(plistlib.dumps(search))
    return journal


def undo(location):
    location = Path(location)
    journal = json.loads(location.read_text(encoding='utf-8'))
    restored, skipped = 0, []
    for entry in journal['entries']:
        if 'before' not in entry or entry.get('state') == 'restored':
            continue
        try:
            if file_key(entry['path']) != entry['identity']:
                raise ValueError('文件已替换或离线')
            current = read_tags(entry['path'])
            own = lambda tags: [t for t in tags if t.startswith(journal['prefix'])]
            if own(current) != own(entry['after']):
                raise ValueError('本项目标签已被后续操作更改')
            desired = [t for t in current if not t.startswith(journal['prefix'])] + own(entry['before'])
            write_tags(entry['path'], desired)
            entry['state'] = 'restored'
            restored += 1
            save_json(location, journal)
        except Exception as error:
            skipped.append(entry['path'] + '：' + str(error))
    return restored, skipped
