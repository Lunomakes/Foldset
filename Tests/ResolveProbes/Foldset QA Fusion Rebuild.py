# -*- coding: utf-8 -*-
"""Foldset QA Fusion rebuild, two runs. Run from Resolve: Workspace → Scripts → Foldset QA Fusion Rebuild.

The automated rebuild left "Foldset QA Fusion <date>" without any Fusion comp after reload
(fusion-check.json: compCount 0), so its 4 scans did not test the Loader dependency. This follows the
2026-10-17 procedure instead, without comp.Lock():
- Run 1 (no comp on the clip yet): adds a Fusion comp and a Loader for media/camera-b.mov wired to
  MediaOut, and records what exists before saving. Fusion may open a file dialog: close it, then run
  this script again.
- Run 2 (comp present): saves, closes and reloads the project, records the comp after reload, runs the
  4 scans and compares them with matrix-verified.json.
Only touches the QA project "Foldset QA Fusion <date>". Log: ~/Library/Application Support/Foldset/Probe/
qa-<date>/fusion-rebuild.json
"""
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

DATE = '20261018'
NAME = 'Foldset QA Fusion ' + DATE
MEDIA = Path.home() / 'Movies' / ('Foldset QA ' + DATE) / 'media'
LOGS = Path.home() / 'Library/Application Support/Foldset/Probe' / ('qa-' + DATE)
SUPPORT = Path.home() / 'Library/Application Support/Foldset/Resolve'
EXPECTED = {'all-strict': [1, 0, 2], 'all-ignore': [1, 0, 2], 'current-strict': [1, 0, 2], 'current-ignore': [1, 0, 2]}
LOGS.mkdir(parents=True, exist_ok=True)
LOG = LOGS / 'fusion-rebuild.json'
log = json.loads(LOG.read_text(encoding='utf-8')) if LOG.exists() else {'runs': []}
run = {'at': datetime.now().isoformat()}
log['runs'].append(run)


def save_log():
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')


def tools_of(item):
    result = []
    for index in range(1, (item.GetFusionCompCount() or 0) + 1):
        comp = item.GetFusionCompByIndex(index)
        for tool in (comp.GetToolList(False) or {}).values() if comp else []:
            attrs = tool.GetAttrs()
            entry = {'id': attrs.get('TOOLS_RegID'), 'name': attrs.get('TOOLS_Name')}
            if entry['id'] == 'Loader':
                entry['clip'] = tool.GetInput('Clip')
            result.append(entry)
    return result


def clip_item(project):
    timeline = project.GetTimelineByIndex(1)
    assert timeline and project.SetCurrentTimeline(timeline), 'no timeline'
    items = timeline.GetItemListInTrack('video', 1) or []
    assert len(items) == 1, 'expected one clip on V1'
    return items[0]


try:
    if str(SUPPORT) not in sys.path:
        sys.path.insert(0, str(SUPPORT))
    import importlib
    import foldset_usage as usage
    importlib.reload(usage)
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject()
    if not project or project.GetName() != NAME:
        if project:
            manager.SaveProject()
        project = manager.LoadProject(NAME)
    assert project and project.GetName() == NAME, 'cannot open ' + NAME
    item = clip_item(project)
    run['compCountAtStart'] = item.GetFusionCompCount()
    if not run['compCountAtStart']:
        run['stage'] = 1
        comp = item.AddFusionComp()
        assert comp, 'AddFusionComp failed'
        loader = comp.AddTool('Loader')
        assert loader, 'AddTool Loader failed'
        loader.SetInput('Clip', str(MEDIA / 'camera-b.mov'))
        out = next(t for t in comp.GetToolList(False).values() if t.GetAttrs().get('TOOLS_RegID') == 'MediaOut')
        out.ConnectInput('Input', loader)
        run['compCountAfterAdd'] = item.GetFusionCompCount()
        run['toolsBeforeSave'] = tools_of(item)
        run['next'] = 'Close any Fusion file dialog, then run Foldset QA Fusion Rebuild again.'
    else:
        run['stage'] = 2
        run['toolsBeforeSave'] = tools_of(item)
        run['saved'] = bool(manager.SaveProject())
        assert manager.CloseProject(manager.GetCurrentProject()), 'close failed'
        project = manager.LoadProject(NAME)
        assert project, 'reload failed'
        item = clip_item(project)
        run['compCountAfterReload'] = item.GetFusionCompCount()
        run['toolsAfterReload'] = tools_of(item)
        run['counts'], run['blockers'], run['mismatches'] = {}, {}, []
        for scope in ('all', 'current'):
            for ignore in (False, True):
                key = scope + ('-ignore' if ignore else '-strict')
                report = usage.scan(project, scope, ignore_compounds=ignore, disk_folder=str(MEDIA))
                got = [sum(r['status'] == s for r in report['records']) for s in ('used', 'unused', 'unknown')]
                run['counts'][key], run['blockers'][key] = got, report['blockers']
                if got != EXPECTED[key]:
                    run['mismatches'].append({'case': key, 'expected': EXPECTED[key], 'got': got})
        run['matched'] = not run['mismatches']
except Exception:
    run['error'] = traceback.format_exc()
save_log()
print('Foldset QA Fusion rebuild stage %s: %s' % (run.get('stage'), run.get('next') or ('matched=%s' % run.get('matched'))))
