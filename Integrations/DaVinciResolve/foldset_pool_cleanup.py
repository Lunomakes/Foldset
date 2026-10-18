"""Remove only prevalidated, successfully trashed unused media-pool entries."""
from pathlib import Path
from datetime import datetime
import uuid
import foldset_usage as usage
from foldset_tags import save_json

BACKUPS=Path.home()/'Library/Application Support/Foldset/Resolve/ProjectBackups'

def inventory(project):
    pending=[project.GetMediaPool().GetRootFolder()];result={}
    while pending:
        folder=pending.pop();clips=folder.GetClipList();children=folder.GetSubFolderList()
        if clips is None or children is None:raise ValueError('媒体池读取不完整，已停止联动清理。')
        pending.extend(children)
        for clip in clips:result[clip.GetUniqueId()]=clip
    return result

def timeline_state(project):
    rows=[]
    for n in range(1,project.GetTimelineCount()+1):
        timeline=project.GetTimelineByIndex(n)
        for kind in ('video','audio'):
            for track in range(1,timeline.GetTrackCount(kind)+1):
                clips=timeline.GetItemListInTrack(kind,track)
                if clips is None:raise ValueError('时间线读取不完整。')
                for clip in clips:
                    media=clip.GetMediaPoolItem()
                    rows.append((timeline.GetUniqueId(),kind,track,clip.GetUniqueId(),media.GetUniqueId() if media else None,clip.GetStart(),clip.GetEnd()))
    return rows

def prepare(resolve,batch):
    project=resolve.GetProjectManager().GetCurrentProject()
    strict=usage.scan(project,'all',ignore_compounds=False)
    eligible={r['identity'] for r in strict['records'] if r['status']=='unused' and not r['positiveUsage'] and not r['missingUsage']}
    if any(e['fingerprint'][0] not in eligible for e in batch['entries']):
        raise ValueError('联动清理已停止：部分素材在全部时间线中仍被使用或依赖待核实。请关闭“忽略复合片段”并重新扫描确认。文件尚未移到废纸篓。')
    clips=inventory(project);mapping={}
    for id,clip in clips.items():
        props=clip.GetClipProperty();key=usage.file_key(props.get('File Path',''))
        if key in eligible:mapping.setdefault(key,[]).append(id)
    for e in batch['entries']:
        e['mediaPoolIds']=mapping.get(e['fingerprint'][0],[])
        if not e['mediaPoolIds']:raise ValueError('对应媒体池条目已改变，请重新扫描。')
    batch['projectID']=project.GetUniqueId();batch['timelineState']=timeline_state(project)
    BACKUPS.mkdir(parents=True,exist_ok=True)
    backup=BACKUPS/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.drp')
    if not resolve.GetProjectManager().ExportProject(project.GetName(),str(backup)) or not backup.is_file():
        raise ValueError('项目备份未成功，未执行联动清理。')
    batch['projectBackup']=str(backup)

def finish(resolve,batch,journal):
    project=resolve.GetProjectManager().GetCurrentProject();removed=0;errors=[]
    if project.GetUniqueId()!=batch['projectID'] or timeline_state(project)!=batch['timelineState']:
        return 0,['项目或时间线已变化，未移除媒体池条目。']
    clips=inventory(project);pool=project.GetMediaPool()
    for e in batch['entries']:
        if e['state']!='trashed':continue
        e['poolRemovedIds']=[]
        for id in e['mediaPoolIds']:
            clip=clips.get(id)
            if not clip:continue
            if str(clip.GetClipProperty().get('Usage',''))!='0':
                errors.append('媒体池引用状态变化，保留条目：'+clip.GetName());continue
            # One item at a time; verify actual disappearance, not just return value.
            pool.DeleteClips([clip])
            if id in inventory(project):errors.append('媒体池未移除：'+clip.GetName())
            else:e['poolRemovedIds'].append(id);removed+=1
            save_json(journal,batch)
    batch['poolCleanup']={'removed':removed,'errors':errors};save_json(journal,batch)
    return removed,errors
