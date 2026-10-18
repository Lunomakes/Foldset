# -*- coding: utf-8 -*-
"""Foldset QA rebuild. Run from Resolve: Workspace → Scripts → Foldset QA Rebuild.

Recreates the three dependency QA projects of 2026-10-17 (Fusion Loader, compound clip,
multicam), saves and reloads each, runs the 12 scan combinations with the installed
foldset_usage.scan, and compares the counts with output/QA/dependencies-20261017/matrix-verified.json.
Then creates "Foldset QA Files <date>" for the move / trash / cleanup checks and leaves it open.

Safety:
- Uses only copies under ~/Movies/Foldset QA <date>/ (prepared beforehand); output/QA is never read
  or written by Resolve.
- Refuses to start unless the open project is a throwaway one (name starts with 新建项目, Untitled
  Project or Foldset QA), because it saves and closes that project first.
- Refuses if any project it would create already exists. Creates projects only; deletes nothing.
- Locks the Fusion comp while adding the Loader so no file dialog opens.
  Known issue (2026-10-18): the Fusion project built this way had no comp after reload, so its 4 scans
  did not test the Loader. Use "Foldset QA Fusion Rebuild.py" (two runs, no lock) for that project.
Logs: ~/Library/Application Support/Foldset/Probe/qa-<date>/ (progress.json, results.json)
"""
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

DATE = '20261018'
ROOT = Path.home() / 'Movies' / ('Foldset QA ' + DATE)
MEDIA = ROOT / 'media'
FILES = ROOT / 'files'
LOGS = Path.home() / 'Library/Application Support/Foldset/Probe' / ('qa-' + DATE)
SUPPORT = Path.home() / 'Library/Application Support/Foldset/Resolve'
# [used, unused, unknown] per reloaded project, from matrix-verified.json of 2026-10-17.
EXPECTED = {'Fusion': {'all-strict': [1, 0, 2], 'all-ignore': [1, 0, 2], 'current-strict': [1, 0, 2], 'current-ignore': [1, 0, 2]},
            'Compound': {'all-strict': [1, 0, 2], 'all-ignore': [1, 2, 0], 'current-strict': [0, 0, 3], 'current-ignore': [0, 3, 0]},
            'Multicam': {'all-strict': [2, 0, 1], 'all-ignore': [2, 1, 0], 'current-strict': [0, 0, 3], 'current-ignore': [0, 3, 0]}}
SAFE_PREFIXES = ('新建项目', 'Untitled Project', 'Foldset QA')

LOGS.mkdir(parents=True, exist_ok=True)
results = {'startedAt': datetime.now().isoformat(), 'current': None, 'projects': {}, 'mismatches': []}


def write(name, data):
    path = LOGS / name
    temp = path.with_suffix('.tmp')
    with open(temp, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def step(name):
    results['current'] = name
    write('progress.json', results)
    print('Foldset QA: ' + name)


def counts(report):
    return [sum(r['status'] == s for r in report['records']) for s in ('used', 'unused', 'unknown')]


try:
    if str(SUPPORT) not in sys.path:
        sys.path.insert(0, str(SUPPORT))
    import importlib
    import foldset_usage as usage
    importlib.reload(usage)
    manager = resolve.GetProjectManager()
    step('preflight')
    for name in ('camera-a.mov', 'camera-b.mov', 'unused-control.mov'):
        assert (MEDIA / name).is_file(), 'missing copy: ' + str(MEDIA / name)
    for name in ('used.mov', 'unused-a.mov', 'unused-b.mov', 'unimported.mov'):
        assert (FILES / name).is_file(), 'missing copy: ' + str(FILES / name)
    current = manager.GetCurrentProject()
    assert current, 'open a throwaway project first'
    assert current.GetName().startswith(SAFE_PREFIXES), 'refusing: current project is not a throwaway project: ' + current.GetName()
    names = ['Foldset QA %s %s' % (kind, DATE) for kind in ('Fusion', 'Compound', 'Multicam', 'Files')]
    existing = set(manager.GetProjectListInCurrentFolder() or [])
    clash = [n for n in names if n in existing]
    assert not clash, 'refusing: projects already exist: ' + ', '.join(clash)

    def fresh(name):
        assert manager.SaveProject(), 'could not save the open project'
        assert manager.CloseProject(manager.GetCurrentProject()), 'could not close the open project'
        project = manager.CreateProject(name, str(ROOT / 'generated'))
        assert project and project.GetName() == name, 'could not create ' + name
        return project

    for kind in ('Fusion', 'Compound', 'Multicam'):
        name = 'Foldset QA %s %s' % (kind, DATE)
        entry = results['projects'][kind] = {'project': name}
        try:
            step(kind + '.build')
            project = fresh(name)
            pool = project.GetMediaPool()
            clips = pool.ImportMedia([str(MEDIA / n) for n in ('camera-a.mov', 'camera-b.mov', 'unused-control.mov')])
            assert clips and len(clips) == 3, 'import failed'
            byname = {c.GetName(): c for c in clips}
            timeline = pool.CreateEmptyTimeline('QA ' + kind)
            assert timeline and project.SetCurrentTimeline(timeline)
            if kind == 'Multicam':
                multicam = pool.CreateMulticamClip([byname['camera-a.mov'], byname['camera-b.mov']], {
                    'name': 'QA Multicam', 'frameRate': 24.0, 'angleSyncMode': resolve.MULTICAM_ANGLE_SYNC_IN,
                    'angleNameMode': resolve.MULTICAM_ANGLE_NAME_SEQUENTIAL, 'createBinForSourceClips': False})
                assert multicam and len(multicam) == 1, 'multicam failed'
                assert pool.AppendToTimeline([{'mediaPoolItem': multicam[0]}]), 'append failed'
            else:
                placed = pool.AppendToTimeline([{'mediaPoolItem': byname['camera-a.mov']}])
                assert placed, 'append failed'
                if kind == 'Compound':
                    assert timeline.CreateCompoundClip(placed, {'name': 'QA Compound'}), 'compound failed'
                else:
                    comp = placed[0].AddFusionComp()
                    assert comp, 'fusion comp failed'
                    comp.Lock()  # no file dialog for the new Loader
                    try:
                        loader = comp.AddTool('Loader')
                        assert loader, 'loader failed'
                        loader.SetInput('Clip', str(MEDIA / 'camera-b.mov'))
                        out = next(t for t in comp.GetToolList(False).values() if t.GetAttrs().get('TOOLS_RegID') == 'MediaOut')
                        out.ConnectInput('Input', loader)
                    finally:
                        comp.Unlock()
            assert manager.SaveProject(), 'save failed'
            step(kind + '.reload')
            assert manager.CloseProject(manager.GetCurrentProject()), 'close failed'
            project = manager.LoadProject(name)
            assert project, 'reload failed'
            assert project.SetCurrentTimeline(project.GetTimelineByIndex(1)), 'no timeline after reload'
            entry['counts'] = {}
            for scope in ('all', 'current'):
                for ignore in (False, True):
                    key = scope + ('-ignore' if ignore else '-strict')
                    step(kind + '.scan.' + key)
                    report = usage.scan(project, scope, ignore_compounds=ignore, disk_folder=str(MEDIA))
                    entry['counts'][key] = counts(report)
                    entry.setdefault('blockers', {})[key] = report['blockers']
                    if entry['counts'][key] != EXPECTED[kind][key]:
                        results['mismatches'].append({'project': kind, 'case': key,
                                                      'expected': EXPECTED[kind][key], 'got': entry['counts'][key]})
            entry['ok'] = True
        except Exception:
            entry['error'] = traceback.format_exc()
        write('results.json', results)

    step('Files.build')
    project = fresh('Foldset QA Files ' + DATE)
    pool = project.GetMediaPool()
    clips = pool.ImportMedia([str(FILES / n) for n in ('used.mov', 'unused-a.mov', 'unused-b.mov')])
    assert clips and len(clips) == 3, 'files import failed'
    used = next(c for c in clips if c.GetName() == 'used.mov')
    timeline = pool.CreateEmptyTimeline('QA Files')
    assert timeline and project.SetCurrentTimeline(timeline)
    assert pool.AppendToTimeline([{'mediaPoolItem': used}]), 'files append failed'
    assert manager.SaveProject(), 'files save failed'
    results['projects']['Files'] = {'project': project.GetName(), 'ok': True}
except Exception:
    results['fatal'] = traceback.format_exc()

results['current'] = None
results['finishedAt'] = datetime.now().isoformat()
results['matched'] = (not results['mismatches'] and 'fatal' not in results
                      and all(p.get('ok') for p in results['projects'].values()))
write('progress.json', results)
write('results.json', results)
print('Foldset QA finished. matched=%s  log: %s' % (results['matched'], LOGS / 'results.json'))
