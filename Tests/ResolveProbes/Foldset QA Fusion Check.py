# -*- coding: utf-8 -*-
"""Foldset QA Fusion check. Run from Resolve: Workspace → Scripts → Foldset QA Fusion Check.

Read-only diagnostic for "Foldset QA Fusion <date>": loads that project, lists the Fusion comps and
tools on its timeline items (with each Loader's Clip input) and what foldset_usage reports for them.
Changes nothing; it only switches the open project to that QA project.
Log: ~/Library/Application Support/Foldset/Probe/qa-<date>/fusion-check.json
"""
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

DATE = '20261018'
NAME = 'Foldset QA Fusion ' + DATE
LOGS = Path.home() / 'Library/Application Support/Foldset/Probe' / ('qa-' + DATE)
SUPPORT = Path.home() / 'Library/Application Support/Foldset/Resolve'
LOGS.mkdir(parents=True, exist_ok=True)
out = {'startedAt': datetime.now().isoformat(), 'project': NAME, 'items': []}


def save():
    (LOGS / 'fusion-check.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')


try:
    if str(SUPPORT) not in sys.path:
        sys.path.insert(0, str(SUPPORT))
    import foldset_usage as usage
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject()
    if not project or project.GetName() != NAME:
        if project:
            manager.SaveProject()
        project = manager.LoadProject(NAME)
    assert project, 'cannot load ' + NAME
    timeline = project.GetTimelineByIndex(1)
    assert timeline, 'no timeline'
    project.SetCurrentTimeline(timeline)
    for track in range(1, (timeline.GetTrackCount('video') or 0) + 1):
        for item in timeline.GetItemListInTrack('video', track) or []:
            entry = {'track': track, 'name': item.GetName(), 'compCount': item.GetFusionCompCount(),
                     'compNames': item.GetFusionCompNameList(), 'comps': []}
            for index in range(1, (item.GetFusionCompCount() or 0) + 1):
                comp = item.GetFusionCompByIndex(index)
                tools = []
                for tool in (comp.GetToolList(False) or {}).values() if comp else []:
                    attrs = tool.GetAttrs()
                    info = {'id': attrs.get('TOOLS_RegID'), 'name': attrs.get('TOOLS_Name')}
                    if info['id'] == 'Loader':
                        try:
                            info['clip'] = tool.GetInput('Clip')
                        except Exception as error:
                            info['clip'] = repr(error)
                    tools.append(info)
                entry['comps'].append({'index': index, 'tools': tools})
            entry['foldsetReason'] = usage.fusion_dependency_reason(item)
            out['items'].append(entry)
    out['scan'] = {k: v for k, v in usage.scan(project, 'all', disk_folder=str(Path.home() / 'Movies' / ('Foldset QA ' + DATE) / 'media')).items()
                   if k in ('blockers', 'skipped')}
except Exception:
    out['error'] = traceback.format_exc()
out['finishedAt'] = datetime.now().isoformat()
save()
print('Foldset QA Fusion check: ' + str(LOGS / 'fusion-check.json'))
