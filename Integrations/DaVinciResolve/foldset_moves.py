# -*- coding: utf-8 -*-
"""Journalled, same-volume, no-overwrite moves. No automatic media relinking."""
import ctypes
import json
import os
from pathlib import Path
from datetime import datetime
import uuid
from foldset_usage import file_key
from foldset_tags import save_json

ROOT = Path.home() / 'Library/Application Support/Foldset/Resolve/MoveReports'


def fingerprint(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError('文件不存在或是符号链接：' + str(p))
    s = p.stat()
    return [file_key(str(p)), s.st_size, s.st_mtime_ns]


def rename_exclusive(source, destination):
    libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    fn = libc.renamex_np
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(os.fsencode(source), os.fsencode(destination), 4) != 0:  # RENAME_EXCL
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def plan(records, destination):
    target = Path(destination).resolve(strict=True)
    if not target.is_dir() or not records:
        raise ValueError('请选择文件和目标文件夹。')
    base = Path(os.path.commonpath([str(Path(r['path']).parent) for r in records]))
    entries, destinations = [], set()
    for r in records:
        source = Path(r['path'])
        stamp = fingerprint(source)
        if stamp[0] != r['identity']:
            raise ValueError('源文件已改变，请重新扫描：' + str(source))
        if source.stat().st_dev != target.stat().st_dev:
            raise ValueError('当前只支持同一磁盘内移动，请在源素材所在磁盘选择目标文件夹。')
        dest = target / source.relative_to(base)
        key = str(dest).casefold()
        if key in destinations or os.path.lexists(dest):
            raise ValueError('目标已有同名项目，未移动任何文件：' + str(dest))
        # Resolve existing ancestor symlinks before authorizing the plan.
        if not dest.resolve().is_relative_to(target):
            raise ValueError('目标子目录指向文件夹外部，已停止。')
        destinations.add(key)
        entries.append({'source':str(source),'destination':str(dest),'fingerprint':stamp,'state':'planned'})
    return {'version':1,'destination':str(target),'entries':entries,'createdAt':datetime.now().isoformat()}


def execute(batch, root=ROOT):
    # Validate the entire plan again before the first filesystem change.
    for e in batch['entries']:
        if fingerprint(e['source']) != e['fingerprint'] or os.path.lexists(e['destination']):
            raise ValueError('文件或目标已改变，请重新准备移动。')
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    journal = root / (datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json')
    save_json(journal,batch)
    for e in batch['entries']:
        try:
            dest = Path(e['destination'])
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.parent.resolve().is_relative_to(Path(batch['destination'])):
                raise ValueError('目标目录发生变化，停止移动。')
            if fingerprint(e['source']) != e['fingerprint']:
                raise ValueError('源文件发生变化，停止移动。')
            rename_exclusive(e['source'],e['destination'])
            e['state']='moved'
            save_json(journal,batch)
        except Exception as error:
            e['error']=str(error)
            save_json(journal,batch)
            break
    return journal,batch


def restore(journal):
    batch=json.loads(Path(journal).read_text(encoding='utf-8'))
    count,errors=0,[]
    for e in reversed(batch['entries']):
        if e['state']=='restored':
            continue
        # Reconcile a crash between rename and journal update.
        if not os.path.lexists(e['destination']) and e['state']=='planned':
            continue
        try:
            if fingerprint(e['destination']) != e['fingerprint']:
                raise ValueError('移动后的文件被修改或替换，未覆盖')
            if os.path.lexists(e['source']):
                raise ValueError('原位置已存在文件，未覆盖')
            parent=Path(e['source']).parent
            if parent.resolve()!=parent:
                raise ValueError('原目录出现符号链接，未恢复')
            parent.mkdir(parents=True,exist_ok=True)
            rename_exclusive(e['destination'],e['source'])
            e['state']='restored';count+=1
            save_json(journal,batch)
        except Exception as error:
            errors.append(e['source']+'：'+str(error))
    return count,errors


def latest_pending(root=ROOT):
    for p in sorted(Path(root).glob('*.json'),reverse=True):
        data=json.loads(p.read_text(encoding='utf-8'))
        if any(e['state']=='moved' or (e['state']=='planned' and not os.path.lexists(e['source']) and os.path.lexists(e['destination'])) for e in data['entries']):
            return p
    return None
