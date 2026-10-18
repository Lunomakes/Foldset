# -*- coding: utf-8 -*-
"""Read-only usage inventory. A zero Usage value never overrides timeline evidence."""
import hashlib
import json
import os
from datetime import datetime


def file_key(path):
    if not path or not os.path.isabs(path):
        return None
    path = os.path.realpath(path)
    try:
        stat = os.stat(path)
        if not os.path.isfile(path):
            return None
        return '%s:%s' % (stat.st_dev, stat.st_ino)
    except OSError:
        return None


# Only verified built-in processing nodes can be cleared without dependency review.
_PROCESSING_NODES = {
    'GroupOperator', 'MediaOut', 'PipeRouter', 'Transform', 'Background',
    'Dissolve', 'LUTLookup', 'LUTBezier', 'ColorCorrector', 'Shadow', 'Merge',
    'ChannelBoolean', 'Vector', 'FastNoise',
    'ofx.com.blackmagicdesign.resolvefx.DirectionalBlur',
}


def fusion_dependency_reason(item):
    try:
        for index in range(1, (item.GetFusionCompCount() or 0) + 1):
            comp = item.GetFusionCompByIndex(index)
            nodes = comp.GetToolList(False) if comp else None
            if not isinstance(nodes, dict) or not nodes:
                return 'Fusion 节点无法完整读取'
            for node in nodes.values():
                kind = node.GetAttrs().get('TOOLS_RegID')
                if kind == 'MediaIn':
                    if node.GetInput('MediaSource') != 'Timeline':
                        return 'Fusion 包含非时间线媒体输入'
                elif kind not in _PROCESSING_NODES:
                    return 'Fusion 节点依赖待核实：' + str(kind)
        return None
    except Exception:
        return 'Fusion 节点依赖读取失败'


# Deliberately exclude sidecars, stills/image sequences and project documents.
MEDIA_EXTENSIONS = frozenset('.mp4 .mov .mxf .mkv .avi .mts .m2ts .m4v .webm .braw .r3d .wav .mp3 .aif .aiff .m4a .aac .flac .ogg'.split())


def is_excluded(path, folders):
    path = os.path.realpath(path)
    return any(os.path.commonpath([path, folder]) == folder for folder in folders)


def scan(project, scope='all', ignore_compounds=False, disk_folder=None, excluded_folders=None):
    excluded = sorted({os.path.realpath(p) for p in (excluded_folders or [])})
    if not project or scope not in ('all', 'current'):
        raise ValueError('请先打开项目并选择扫描范围。')
    pool = project.GetMediaPool()
    current = project.GetCurrentTimeline()
    if scope == 'current' and not current:
        raise ValueError('请先打开一条时间线。')
    timelines = ([current] if scope == 'current' else
                 [project.GetTimelineByIndex(i) for i in range(1, project.GetTimelineCount() + 1)])
    if not timelines or any(t is None for t in timelines):
        raise ValueError('没有可扫描的时间线。')
    inventory = []
    folders = [pool.GetRootFolder()]
    while folders:
        folder = folders.pop()
        children, clips = folder.GetSubFolderList(), folder.GetClipList()
        if children is None or clips is None:
            raise ValueError('媒体池读取不完整，请稍后重新扫描。')
        folders.extend(children)
        for clip in clips:
            inventory.append({'id': clip.GetUniqueId(), 'name': clip.GetName(),
                              'props': clip.GetClipProperty()})
    used_ids, used_keys, blockers, visited = set(), set(), set(), set()

    ignored = set()

    def mark_media(media):
        used_ids.add(media.GetUniqueId())
        props = media.GetClipProperty()
        path = props.get('File Path', '')
        identity = file_key(path)
        if identity:
            used_keys.add(identity)
        if props.get('Synced Audio'):
            blockers.add('同步音频的依赖不能完整确认')
        # Matte source files can themselves be media-pool sources.
        try:
            for matte in pool.GetClipMatteList(media) or []:
                key = file_key(matte)
                if key:
                    used_keys.add(key)
        except Exception:
            blockers.add('无法完整读取外部遮罩依赖')
        if not path:
            nested = media.GetTimeline()
            if nested:
                walk_timeline(nested)
            else:
                reason = '无法展开复合片段／多机位：' + media.GetName()
                (ignored if ignore_compounds else blockers).add(reason)

    def walk_timeline(timeline):
        tid = timeline.GetUniqueId()
        if tid in visited:
            return
        visited.add(tid)
        for kind in ('video', 'audio', 'subtitle'):
            count = timeline.GetTrackCount(kind)
            if count is None and kind != 'subtitle':
                raise ValueError('无法读取音视频轨道数量，请重试扫描。')
            for track in range(1, (count or 0) + 1):
                items = timeline.GetItemListInTrack(kind, track)
                if items is None:
                    raise ValueError('时间线轨道读取不完整，未生成未使用分类。')
                for item in items:
                    media = item.GetMediaPoolItem()
                    if media:
                        mark_media(media)
                    if kind != 'subtitle':
                        if (item.GetFusionCompCount() or 0) > 0:
                            reason = fusion_dependency_reason(item)
                            if reason:
                                blockers.add(reason + '（' + item.GetName() + '）')
                        for take in range(1, (item.GetTakesCount() or 0) + 1):
                            info = item.GetTakeByIndex(take)
                            if info and info.get('mediaPoolItem'):
                                mark_media(info['mediaPoolItem'])
                            else:
                                blockers.add('备选镜头依赖读取不完整')
    for timeline in timelines:
        walk_timeline(timeline)
    # Positive usage is supplemental evidence only for the whole-project scope.
    if scope == 'all':
        for item in inventory:
            usage = str(item['props'].get('Usage', ''))
            if usage.isdigit() and int(usage) > 0:
                used_ids.add(item['id'])
                identity = file_key(item['props'].get('File Path', ''))
                if identity:
                    used_keys.add(identity)
    records, skipped = {}, []
    for item in inventory:
        path = item['props'].get('File Path', '')
        if not path:
            skipped.append({'name': item['name'], 'reason': '无独立源文件（时间线、复合片段或生成器）'})
            continue
        if is_excluded(path, excluded):
            continue
        identity = file_key(path)
        if not identity:
            skipped.append({'name': item['name'], 'path': path,
                            'reason': '源文件离线、不存在或为序列／目录，未写标签'})
            continue
        record = records.setdefault(identity, {'path': os.path.realpath(path), 'identity': identity,
            'names': [], 'status': 'unused', 'positiveUsage': False, 'missingUsage': False})
        record['names'].append(item['name'])
        usage = str(item['props'].get('Usage', ''))
        record['missingUsage'] |= not usage.isdigit()
        record['positiveUsage'] |= usage.isdigit() and int(usage) > 0
        if identity in used_keys or item['id'] in used_ids:
            record['status'] = 'used'
    for record in records.values():
        if record['status'] != 'used' and (blockers or record['missingUsage']):
            record['status'] = 'unknown'
    disk_root = None
    disk_skipped = 0
    if disk_folder:
        disk_root = os.path.realpath(disk_folder)
        if not os.path.isdir(disk_root):
            raise ValueError('所选素材文件夹不存在或未挂载。')
        def walk_error(error):
            raise ValueError('素材文件夹读取不完整：' + str(error))
        for parent, dirs, files in os.walk(disk_root, followlinks=False, onerror=walk_error):
            if is_excluded(parent, excluded):
                dirs[:] = []
                continue
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not os.path.islink(os.path.join(parent, d)) and not is_excluded(os.path.join(parent, d), excluded))
            for name in sorted(files):
                path = os.path.join(parent, name)
                if name.startswith('.') or os.path.islink(path) or os.path.splitext(name)[1].lower() not in MEDIA_EXTENSIONS:
                    disk_skipped += 1
                    continue
                identity = file_key(path)
                if not identity:
                    raise ValueError('素材文件读取失败，请重新扫描：' + path)
                if identity not in records:
                    records[identity] = {'path': path, 'identity': identity, 'names': [name],
                        'status': 'unknown' if identity in used_keys else 'not_imported',
                        'origin': 'disk', 'positiveUsage': False, 'missingUsage': False}
    result = {'project': project.GetName(), 'projectID': project.GetUniqueId(),
        'scope': scope, 'timelineID': current.GetUniqueId() if scope == 'current' else None,
        'timelines': [t.GetName() for t in timelines], 'scannedAt': datetime.now().isoformat(),
        'records': sorted(records.values(), key=lambda r: r['path']),
        'blockers': sorted(blockers), 'skipped': skipped,
        'diskFolder': disk_root, 'diskSkipped': disk_skipped, 'excludedFolders': excluded,
        'ignoreCompounds': bool(ignore_compounds), 'ignoredDependencies': sorted(ignored)}
    signature_data = {k: v for k, v in result.items() if k != 'scannedAt'}
    result['signature'] = hashlib.sha256(json.dumps(signature_data, sort_keys=True).encode()).hexdigest()
    return result


def summary(report):
    counts = {s: sum(r['status'] == s for r in report['records']) for s in ('used','unused','unknown','not_imported')}
    lines = ['项目：' + report['project'],
             '范围：' + ('全部时间线' if report['scope'] == 'all' else '当前时间线') + '（%d 条）' % len(report['timelines']),
             '绿色 已使用：%d    灰色 未使用候选：%d    黄色 待核实：%d' % (counts['used'],counts['unused'],counts['unknown']),
             '无法标记的媒体池条目：%d' % len(report['skipped']), '',
             '判断按源文件合并。标签是扫描快照，剪辑修改后需重新扫描。',
             '“未使用”仅针对所选范围，不代表其他项目没有引用；不会自动移动或删除文件。']
    if report.get('diskFolder'):
        lines += ['', '对比文件夹：' + report['diskFolder'],
                  '蓝色 未导入当前项目：%d' % counts['not_imported'],
                  '递归对比视频与音频；XML、图片序列等非支持文件不处理（%d 个）。' % report.get('diskSkipped', 0),
                  '未导入仅表示不在当前媒体池，不保证未被 Fusion、其他项目或外部工具引用。']
    if report.get('excludedFolders'):
        lines += ['', '已排除文件夹（含子文件夹）：'] + report['excludedFolders']
    if report['scope'] == 'current':
        lines.append('当前时间线：' + report['timelines'][0] + '；其他时间线可能仍使用这些候选文件。')
    if report.get('ignoreCompounds'):
        lines += ['', '已开启忽略复合片段／多机位：候选文件可能仍被其内部使用。',
                  'Fusion 等其他依赖仍照常检查。'] + report.get('ignoredDependencies', [])
    if report['blockers']:
        lines += ['', '未确认使用的文件已保守归入“待核实”，原因：'] + report['blockers']
    return '\n'.join(lines)
