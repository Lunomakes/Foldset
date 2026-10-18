# -*- coding: utf-8 -*-
"""Preview-first Finder usage tagging; Resolve project data is never modified."""
import html
import os
import subprocess
import foldset_usage as usage
import foldset_tags as tags
import foldset_browser as browser
import foldset_dialogs as dialogs

# Presentation only. Verified in Resolve 21.1.1 : Label/TextEdit HTML colour,
# Tree per-column TextColor and Button StyleSheet work. Font objects crash the host; padding clips; do not use them.
_RGB = {'used':(0.19,0.82,0.35),'unused':(0.6,0.6,0.62),'unknown':(1,0.84,0.04),
        'not_imported':(0.25,0.61,1),'skipped':(0.56,0.56,0.58)}
ROWS = [('used','已使用','绿色标签 · 所选范围内确认使用'),
        ('unused','未使用候选','灰色标签 · 所选范围内未发现使用，不等于可以删除'),
        ('unknown','待核实','黄色标签 · 无法确认是否使用，保守处理'),
        ('not_imported','未导入','蓝色标签 · 在对比文件夹中，但不在当前媒体池'),
        ('skipped','无法标记','不写标签 · 无独立源文件、离线或为序列')]
PRIMARY = dialogs.PRIMARY
status_html = dialogs.status_html


def clean_folder(text):
    """A pasted folder path: trim spaces and one pair of surrounding quotes (as copied from
    Terminal or some Finder tools), expand ~. Empty means no folder."""
    text = (text or '').strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '\'"':
        text = text[1:-1].strip()
    return os.path.expanduser(text) if text else None


def count_rows(report):
    """(kind, title, count or None, meaning) for the result table; None before a scan."""
    if report is None:
        return [(k, t, None, m) for k, t, m in ROWS if k != 'not_imported']
    counts = {k: sum(r['status'] == k for r in report['records']) for k, _, _ in ROWS}
    counts['skipped'] = len(report['skipped'])
    return [(k, t, counts[k], m) for k, t, m in ROWS if k != 'not_imported' or report.get('diskFolder')]


def report_html(report, problems=None, problems_title=None):
    """How this scan decided. Blockers are project-wide in foldset_usage.scan, so they are never
    attributed to single files here."""
    if report is None:
        return ('<p>选择范围后点击“扫描”。扫描只读取项目，不会写标签、移动或删除文件。</p>'
                '<p style="color:#98989d">颜色含义与多个标签的解释见“标签说明…”。</p>')
    e = html.escape
    unknown = sum(r['status'] == 'unknown' for r in report['records'])
    if report['scope'] == 'all':
        scope = '全部时间线（%d 条）' % len(report['timelines'])
    else:
        scope = '当前时间线「%s」；其他时间线可能仍使用这些候选文件' % e(report['timelines'][0])
    lines = ['项目「%s」 · 范围：%s' % (e(report['project']), scope),
             '按源文件合并判断。标签是扫描快照，剪辑修改后需要重新扫描。']
    if report.get('diskFolder'):
        lines.append('对比文件夹 %s：递归对比视频与音频；跳过 %d 个不支持的文件（XML、图片序列等）。'
                     % (dialogs.wrap_path(report['diskFolder']), report.get('diskSkipped', 0)))
    if report.get('excludedFolders'):
        lines.append('已排除 %d 个文件夹（含子文件夹）：%s' % (len(report['excludedFolders']),
                     '、'.join(dialogs.wrap_path(f) for f in report['excludedFolders'])))
    if report.get('ignoreCompounds'):
        lines.append('已忽略无法展开的复合片段／多机位，候选文件可能仍被其内部使用；Fusion 等其他依赖照常检查。'
                     + ''.join('<br>· ' + e(d) for d in report.get('ignoredDependencies', [])))
    out = ['<p><b>这次怎样判定</b></p><ul>'] + ['<li>%s</li>' % line for line in lines] + ['</ul>']
    if report['blockers']:
        out += ['<p style="color:#ffd60a"><b>为什么有 %d 个文件归入“待核实”</b></p>' % unknown,
                '<p>项目中存在下列无法确认的依赖。只要存在任意一项，所有未确认使用的文件都会保守归入“待核实”——'
                '这是对整个项目的判断，不代表每个文件都与这些依赖有关。</p><ul>']
        out += ['<li style="color:#ffd60a">%s</li>' % e(b) for b in report['blockers']] + ['</ul>']
    elif unknown:
        out.append('<p style="color:#ffd60a">%d 个文件缺少可确认的使用信息（例如媒体池用量缺失），已保守归入“待核实”。</p>' % unknown)
    if report.get('diskFolder'):
        out.append('<p style="color:#98989d">“未导入”只表示不在当前媒体池，不保证未被 Fusion、其他项目或外部工具引用。</p>')
    out.append('<p style="color:#98989d">“未使用”只针对所选范围，不代表其他项目没有引用；Foldset 不会自动移动或删除文件。</p>')
    if problems:
        out += ['<p style="color:#ff6961"><b>%s</b></p><ul>' % e(problems_title or '未完成的项目')]
        out += ['<li style="color:#ff6961">%s</li>' % e(p) for p in problems] + ['</ul>']
    return ''.join(out)


def open_window(resolve, bmd):
    ui = resolve.Fusion().UIManager
    # Resolve owns the registry across separately executed script contexts.
    existing = ui.FindWindow("FoldsetFinderUsage")
    if existing:
        existing.Show()
        existing.Raise()
        existing.ActivateWindow()
        return
    dispatcher = bmd.UIDispatcher(ui)
    def button(id, text, width):
        return ui.Button({'ID':id,'Text':text,'Weight':0,
                          'MinimumSize':[width,28],'MaximumSize':[width,28]})
    window = dispatcher.AddWindow({'ID':'FoldsetFinderUsage','WindowFlags':dialogs.PANEL_FLAGS,'WindowTitle':'Foldset · Finder 使用状态',
        'Geometry':[200,140,640,660], 'MinimumSize':[500,560]}, ui.VGroup([
        ui.Label({'Text':'识别当前项目媒体池中的源文件，按使用状态标记到 Finder。','Weight':0,'WordWrap':True}),
        ui.HGroup({'Weight':0,1:ui.Label({'Text':'扫描范围','Weight':0}),
                   2:ui.ComboBox({'ID':'Scope','MaximumSize':[280,28]}),3:button('Scan','扫描',82)}),
        ui.HGroup({'Weight':0,1:ui.LineEdit({'ID':'DiskFolder','MaximumSize':[310,28],'PlaceholderText':'粘贴素材文件夹完整路径（可选）'}),
                   2:button('ChooseFolder','选择…',78),3:button('ClearFolder','清除',58)}),
        ui.HGroup({'Weight':0,1:button('Exclude','排除文件夹…（0）',150),2:ui.Label({'Text':'排除所选文件夹及其子文件夹；不会修改原文件。','WordWrap':True,'Weight':1})}),
        ui.CheckBox({'ID':'IgnoreCompounds','Text':'忽略无法展开的复合片段／多机位依赖','Checked':False,'Weight':0}),
        # Width caps as in the original layout: without them Resolve 21.1.1 lays these out wider
        # than the window and clips the right edge.
        ui.Label({'ID':'Status','Text':'','WordWrap':True,'Weight':0,'MaximumSize':[480,60]}),
        ui.Tree({'ID':'Counts','ColumnCount':3,'RootIsDecorated':False,'Weight':0,'FixedSize':[480,150]}),
        ui.TextEdit({'ID':'Result','ReadOnly':True,'Weight':1,'MinimumSize':[0,120],'MaximumSize':[480,10000]}),
        ui.HGroup({'Weight':0,1:button('Apply','写入 Finder 标签',132),
            2:button('Find','查看未使用候选',124),3:button('Report','查看清单',92),
            4:button('Undo','撤销本次标记',116)}),
        ui.HGroup({'Weight':0,1:button('Browse','素材列表…',114),2:button('FindNotImported','Finder 未导入',124),3:button('Legend','标签说明…',100)})]))
    items = window.GetItems()
    items['Scope'].AddItem('全部时间线（推荐）')
    items['Scope'].AddItem('当前时间线')
    header = items['Counts'].NewItem()
    header.Text[0] = '分类'; header.Text[1] = '数量'; header.Text[2] = '含义'
    items['Counts'].SetHeaderItem(header)
    # Header plus five rows without scrollbars; the meaning column takes the remaining width.
    for column, width in enumerate((84, 48, 330)):
        items['Counts'].ColumnWidth[column] = width
    items['Apply'].StyleSheet = PRIMARY

    def status(text, tone='info'):
        items['Status'].Text = status_html(text, tone)
    def show(report, problems=None, problems_title=None):
        """Fill the count table and the decision trace; layout only, no classification here."""
        tree = items['Counts']
        tree.Clear()
        for kind, title, count, meaning in count_rows(report):
            row = tree.NewItem()
            row.Text[0] = title; row.Text[1] = '–' if count is None else str(count); row.Text[2] = meaning
            if count:
                r, g, b = _RGB[kind]
                for column in (0, 1):
                    row.TextColor[column] = {'R':r,'G':g,'B':b,'A':1}
            tree.AddTopLevelItem(row)
        items['Result'].HTML = report_html(report, problems, problems_title)
    show(None)
    status('尚未扫描')
    state = {'scan':None,'folder':None,'journal':None,'applied':False,'busy':False,'disk':None,'choosing':False,'excluded':[]}
    ACTIONS = ('Apply','Find','FindNotImported','Report','Undo','Browse')
    INPUTS = ('ChooseFolder','DiskFolder','Scan','Scope','IgnoreCompounds')
    for key in ACTIONS:
        items[key].Enabled = False

    def scope(): return 'all' if items['Scope'].CurrentIndex == 0 else 'current'
    def run_scan():
        return usage.scan(resolve.GetProjectManager().GetCurrentProject(), scope(), ignore_compounds=bool(items['IgnoreCompounds'].Checked), disk_folder=state['disk'], excluded_folders=state['excluded'])
    def busy(value):
        state['busy'] = value
        items['Exclude'].Enabled = not value and bool(state['disk'])
        for key in INPUTS + ('ClearFolder',):
            items[key].Enabled = not value
        for key in ACTIONS:
            items[key].Enabled = False
    def has_search(status, name):
        return bool(state['applied'] and state['scan'] and
            any(r['status']==status for r in state['scan']['records']) and
            (state['folder']/name).exists())
    def controls():
        items['Exclude'].Enabled = bool(state['disk'])
        items['Exclude'].Text = '排除文件夹…（%d）'%len(state['excluded'])
        items['Exclude'].ToolTip = '\n'.join(state['excluded']) or '尚未排除文件夹'
        for key in INPUTS:
            items[key].Enabled = True
        items['ClearFolder'].Enabled = bool(state['disk'])
        items['Apply'].Enabled = state['scan'] is not None and bool(state['scan']['records']) and not state['applied']
        items['Browse'].Enabled = state['scan'] is not None
        items['Report'].Enabled = state['folder'] is not None
        items['Undo'].Enabled = state['journal'] is not None
        items['Find'].Enabled = has_search('unused', '未使用候选.savedSearch')
        items['FindNotImported'].Enabled = has_search('not_imported', '未导入当前项目.savedSearch')
        state['busy'] = False
    def invalidate(event):
        if state['scan'] is None:
            return
        state['scan'] = None
        for key in ('Browse','Apply','Find','FindNotImported'):
            items[key].Enabled = False
        status('扫描选项已改变，请重新扫描。', 'warn')
    def choose_folder(event):
        if state['busy'] or state['choosing']:
            return
        state['choosing'] = True
        try:
            selected = resolve.Fusion().RequestDir(state['disk'] or '')
            if selected:
                if selected != state['disk']:state['excluded']=[]
                state['disk'] = selected
                items['DiskFolder'].Text = selected
                invalidate(event)
                controls()
        except Exception as error:
            status('选择文件夹失败：' + str(error), 'bad')
        finally:
            state['choosing'] = False
            window.Show()
            window.Raise()
            window.ActivateWindow()

    def folder_changed(event):
        new_folder = clean_folder(items['DiskFolder'].Text)
        if new_folder != state['disk']:state['excluded']=[]
        state['disk'] = new_folder
        invalidate(event)
        controls()
    def clear_folder(event):
        state['disk'] = None
        state['excluded'] = []
        items['DiskFolder'].Text = ''
        invalidate(event)
        controls()
    def exclude(event):
        if state['busy'] or state['choosing'] or not state['disk']:return
        state['choosing']=True;window.Enabled=False
        try:
            selected=dialogs.choose_exclusions(resolve,bmd,state['disk'],state['excluded'])
            if selected is not None:
                state['excluded']=selected;invalidate(event)
        except Exception as error:status('排除文件夹设置失败：'+str(error), 'bad')
        finally:
            state['choosing']=False;window.Enabled=True;controls();window.Raise();window.ActivateWindow()
    def scan(event):
        busy(True)
        status('正在读取时间线与源文件…')
        try:
            report = run_scan()
            state['scan'] = report
            state['folder'] = tags.prepare_report(report)
            state['applied'] = False
            show(report)
            status('扫描完成，尚未写入标签。请核对范围和结果后再写入。', 'ok')
        except Exception as error:
            state['scan'] = None
            status('扫描失败：' + str(error), 'bad')
        finally:
            controls()
    def apply(event):
        if state['busy'] or state['scan'] is None:
            return
        busy(True)
        try:
            fresh = run_scan()
            if fresh['signature'] != state['scan']['signature']:
                state['scan'] = fresh
                state['folder'] = tags.prepare_report(fresh)
                show(fresh)
                status('项目、时间线或文件状态有变化，已更新结果。请核对后再次点击写入。', 'warn')
                return
            state['applied'] = True
            journal = tags.apply(fresh, state['folder'])
            state['journal'] = state['folder']/'tag-journal.json'
            succeeded = sum(e['state']=='applied' for e in journal['entries'])
            failed = len(journal['entries'])-succeeded
            status('已标记 %d 个文件；失败 %d 个。可撤销本次标记。Finder 搜索依赖 Spotlight 索引，完整路径见清单。' % (succeeded,failed), 'bad' if failed else 'ok')
            if failed:
                show(fresh, [e['path']+'：'+e.get('error','未完成') for e in journal['entries'] if e['state']!='applied'], '写入失败')
        except Exception as error:
            if state['folder'] and (state['folder']/'tag-journal.json').exists():
                state['journal'] = state['folder']/'tag-journal.json'
            status('标记未完成：'+str(error)+'；如有部分写入，可撤销本次标记。', 'bad')
        finally:
            controls()
    def find(event):
        if state['folder']:
            subprocess.run(['/usr/bin/open',str(state['folder']/'未使用候选.savedSearch')],check=True)
    def report(event):
        if state['folder']:
            subprocess.run(['/usr/bin/open',str(state['folder'])],check=True)
    def undo(event):
        if not state['journal']:
            return
        busy(True)
        try:
            count, errors = tags.undo(state['journal'])
            status('已撤销 %d 个文件的本次标签；跳过 %d 个。' % (count,len(errors)), 'warn' if errors else 'ok')
            if errors:
                show(state['scan'], errors, '撤销时跳过')
            else:
                state['journal'] = None
                state['applied'] = False
                state['scan'] = None
        except Exception as error:
            status('撤销失败：'+str(error), 'bad')
        finally:
            controls()
    def legend(event):
        window.Enabled=False
        try:dialogs.show_legend(resolve,bmd)
        finally:window.Enabled=True;window.Raise();window.ActivateWindow()
    window.On['Exclude'].Clicked=exclude
    window.On['Legend'].Clicked=legend
    def browse(event):
        if not state['scan']:
            return
        try:
            browser.open_window(resolve,bmd,state['scan'],lambda: invalidate(None))
        finally:
            # Like the other child windows: bring this window back, or it stays behind
            # Resolve's main window after an app switch.
            window.Show();window.Raise();window.ActivateWindow()
    window.On['Browse'].Clicked = browse
    window.On['ChooseFolder'].Clicked = choose_folder
    window.On['DiskFolder'].TextChanged = folder_changed
    window.On['ClearFolder'].Clicked = clear_folder
    window.On['FindNotImported'].Clicked = lambda event: subprocess.run(['/usr/bin/open', str(state['folder']/'未导入当前项目.savedSearch')], check=True)
    window.On['IgnoreCompounds'].Clicked = invalidate
    window.On['Scope'].CurrentIndexChanged = invalidate
    window.On['Scan'].Clicked = scan
    window.On['Apply'].Clicked = apply
    window.On['Find'].Clicked = find
    window.On['Report'].Clicked = report
    window.On['Undo'].Clicked = undo
    window.On['FoldsetFinderUsage'].Close = lambda event: state.update(closed=True)
    controls()
    try:
        window.Show()
        window.Geometry = [200,140,640,660]
        dialogs.run_window_events(ui,dispatcher,'FoldsetFinderUsage',state,resolve)
    finally:
        window.Hide()
        window.ID="FoldsetFinderUsageClosed"
