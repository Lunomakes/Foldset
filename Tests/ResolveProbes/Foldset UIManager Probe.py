# -*- coding: utf-8 -*-
"""Foldset UIManager capability probe, v2. Run from Resolve: Workspace → Scripts → Foldset UIManager Probe.

Read-only: does not open, read or change any project, media pool, timeline or file except its own logs.

v1 crashed Resolve 21.1.1 (SIGSEGV in Fusion::ScriptVal::From<QFont>, LogArchive/ResolveDebug_C1.txt)
while reading back a Font property / using a ui.Font object. v2 therefore:
- builds widgets with the same plain properties the shipped Foldset windows already use;
- applies each styling probe as its own step, one per click on 下一步, so painting happens in between
  (a ui.Timer bound via dispatcher.On never fired in 21.1.1, so stepping is manual);
- writes progress.json to disk before and after every step. If Resolve crashes, the step left
  "started" is recorded as the crash on the next run and skipped, so each rerun gets further;
- never reads back Font or other object-valued properties, and uses dict fonts only.
Logs: ~/Library/Application Support/Foldset/Probe/
"""
import json
import os
import traceback
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / 'Library/Application Support/Foldset/Probe'
PROGRESS = LOG_DIR / 'progress.json'
LOG_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path, data):
    """Durable write: the file must survive a host crash right after this call."""
    temp = path.with_suffix('.tmp')
    with open(temp, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


previous = {}
if PROGRESS.exists():
    try:
        previous = json.loads(PROGRESS.read_text(encoding='utf-8'))
    except Exception:
        previous = {}
crashed = set(previous.get('crashed', []))
if previous.get('current'):
    crashed.add(previous['current'])  # last run died inside this step

state = {'startedAt': datetime.now().isoformat(), 'crashed': sorted(crashed), 'current': None,
         'host': {}, 'widgets': {}, 'steps': []}
try:
    state['host'] = {'product': resolve.GetProductName(), 'version': resolve.GetVersionString()}
except Exception as error:
    state['host'] = {'error': repr(error)}


def mark(step_id, **fields):
    state['current'] = step_id
    state['steps'].append(dict({'step': step_id, 'at': datetime.now().isoformat()}, **fields))
    write_json(PROGRESS, state)


ui = resolve.Fusion().UIManager
dispatcher = bmd.UIDispatcher(ui)

# Existence only: getattr does not construct anything.
for name in ['Label', 'Button', 'TextEdit', 'Tree', 'Timer', 'HGap', 'VGap', 'Separator', 'Font', 'Icon']:
    try:
        state['widgets'][name] = callable(getattr(ui, name, None))
    except Exception as error:
        state['widgets'][name] = repr(error)
mark('widgets-listed')


def label(text, id=None):
    props = {'Text': text, 'WordWrap': True, 'Weight': 0}
    if id:
        props['ID'] = id
    return ui.Label(props)


# Construction uses only properties already shipped in Foldset's windows.
mark('build-window')
window = dispatcher.AddWindow({'ID': 'FoldsetUIManagerProbe', 'WindowTitle': 'Foldset · UIManager 探测 v2',
                               'Geometry': [220, 120, 560, 720]}, ui.VGroup([
    label('反复点击“下一步”，每次应用一项。进度显示“完成”后，请截取整个窗口，再点击“完成并记录”。', 'Intro'),
    label('P1 预期：“粗体”加粗，“绿色”为绿色（Label HTML）'),
    label('P1 尚未应用', 'P1'),
    label('P2 预期：深灰圆角卡片、浅色文字、内边距（Label StyleSheet）'),
    label('P2 尚未应用', 'P2'),
    label('P3 预期：等宽字体（Label Font，字典写法）'),
    label('P3 尚未应用', 'P3'),
    label('P4 预期：白底黑字胶囊按钮（Button StyleSheet）'),
    ui.Button({'ID': 'P4', 'Text': '扫描', 'Weight': 0, 'MinimumSize': [96, 28], 'MaximumSize': [96, 28]}),
    label('P5 预期：三列表格；“已使用”行绿字，“待核实”行黄字，“未导入”行背景略亮'),
    ui.Tree({'ID': 'P5', 'ColumnCount': 3, 'RootIsDecorated': False, 'Weight': 0,
             'MinimumSize': [460, 130], 'MaximumSize': [10000, 130]}),
    label('P6 预期：富文本列表，粗体标题，第一条为黄色（TextEdit HTML）'),
    ui.TextEdit({'ID': 'P6', 'ReadOnly': True, 'Weight': 0, 'MinimumSize': [460, 90], 'MaximumSize': [10000, 90]}),
    label('进度：准备中', 'Progress'),
    ui.HGroup({'Weight': 0, 1: ui.Label({'Text': '', 'Weight': 1}),
               2: ui.Button({'ID': 'Next', 'Text': '下一步', 'Weight': 0}),
               3: ui.Button({'ID': 'Done', 'Text': '完成并记录', 'Weight': 0})}),
]))
items = window.GetItems()


def p1():
    items['P1'].Text = '<b>粗体</b> · <span style="color:#30d158">绿色</span> · 01_视频素材'


def p2():
    items['P2'].Text = '已使用 53 · 待核实 117'
    items['P2'].StyleSheet = ('color:#f2f2f3; background-color:#232227; border:1px solid #3a3940;'
                              'border-radius:14px; padding:10px; font-size:15px;')


def p3():
    items['P3'].Text = '/Volumes/QA/media/camera-b.mov'
    items['P3'].Font = {'Family': 'Menlo', 'PixelSize': 12}


def p4():
    items['P4'].StyleSheet = 'QPushButton{background:#f2f2f3; color:#111112; border-radius:14px; font-weight:600;}'


def p5_rows():
    tree = items['P5']
    header = tree.NewItem()
    header.Text[0] = '分类'; header.Text[1] = '数量'; header.Text[2] = '含义'
    tree.SetHeaderItem(header)
    for name, count, meaning in (('已使用', '53', '时间线中确认使用'), ('待核实', '117', '项目中有无法确认的依赖'),
                                 ('未导入', '4', '不在当前媒体池')):
        item = tree.NewItem()
        item.Text[0] = name; item.Text[1] = count; item.Text[2] = meaning
        tree.AddTopLevelItem(item)


def tree_item(row):
    return items['P5'].TopLevelItem(row)


def p5_text_color():
    for row, color in ((0, {'R': 0.19, 'G': 0.82, 'B': 0.35, 'A': 1}), (1, {'R': 1, 'G': 0.84, 'B': 0.04, 'A': 1})):
        item = tree_item(row)
        for column in range(3):
            item.TextColor[column] = color


def p5_background():
    item = tree_item(2)
    for column in range(3):
        item.BackgroundColor[column] = {'R': 0.18, 'G': 0.17, 'B': 0.2, 'A': 1}


def p6():
    items['P6'].HTML = ('<p><b>为什么归入待核实</b></p><ul><li style="color:#ffd60a">Fusion 节点依赖待核实：Loader（camera-a.mov）</li>'
                        '<li>无法展开复合片段／多机位：Compound Clip 1</li></ul>')


def read_strings():
    # Strings only. Reading Font back is what crashed v1.
    return {'P1.Text': str(items['P1'].Text), 'P2.StyleSheet': str(items['P2'].StyleSheet),
            'P6.PlainText': str(items['P6'].PlainText)}


# Safest first, so a crash costs as little as possible.
STEPS = [('P1-html', p1), ('P2-stylesheet', p2), ('P4-button-stylesheet', p4), ('P5-rows', p5_rows),
         ('P6-html', p6), ('P5-text-color', p5_text_color), ('P5-background', p5_background),
         ('P3-font-dict', p3), ('read-strings', read_strings)]
queue = [step for step in STEPS if step[0] not in crashed]
for step_id, _ in STEPS:
    if step_id in crashed:
        state['steps'].append({'step': step_id, 'result': 'skipped: crashed Resolve in an earlier run'})


def run_next():
    """Close out the previous step (it survived a paint), then start one more."""
    if state['current'] and state['current'] not in ('widgets-listed', 'build-window'):
        state['steps'].append({'step': state['current'], 'result': 'survived'})
    if not queue:
        state['current'] = None
        write_json(PROGRESS, state)
        items['Progress'].Text = '进度：完成（跳过 %d 项曾导致闪退的步骤）' % len(crashed)
        items['Next'].Enabled = False
        return False
    step_id, action = queue.pop(0)
    mark(step_id)
    items['Progress'].Text = '进度：已应用 %s（还剩 %d 项）' % (step_id, len(queue))
    try:
        value = action()
        state['steps'].append({'step': step_id, 'ok': True, 'value': value})
    except Exception:
        state['steps'].append({'step': step_id, 'ok': False, 'error': traceback.format_exc(limit=1)})
    write_json(PROGRESS, state)
    return True


def finish(event=None):
    if state.get('finishedAt'):
        return
    state['finishedAt'] = datetime.now().isoformat()
    state['current'] = None
    write_json(PROGRESS, state)
    write_json(LOG_DIR / ('uimanager-probe-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.json'), state)
    dispatcher.ExitLoop()


window.On['Done'].Clicked = finish
window.On['FoldsetUIManagerProbe'].Close = finish
window.Show()
state['steps'].append({'step': 'build-window', 'result': 'survived'})
state['current'] = None
write_json(PROGRESS, state)

items['Progress'].Text = '进度：请点击“下一步”（共 %d 项）' % len(queue)
window.On['Next'].Clicked = lambda event: run_next()
dispatcher.RunLoop()
window.Hide()
