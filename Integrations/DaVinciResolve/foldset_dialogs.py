"""Resolve UIManager dialogs; filesystem work runs off the UI thread."""
import html
import threading
import queue
import time
import uuid
from pathlib import Path

def button(ui,id,text):
    return ui.Button({'ID':id,'Text':text,'Weight':0,'MinimumSize':[140,28],'MaximumSize':[180,28]})


# Shared look, limited to what Resolve 21.1.1 renders reliably:
# HTML colour in Label/TextEdit and Button StyleSheet. No Font objects, padding or timers.
TONES={'ok':'#30d158','warn':'#ffd60a','bad':'#ff6961','info':'#98989d','blue':'#409cff'}
PRIMARY=('QPushButton{background:#f2f2f3;color:#111112;border-radius:14px;font-weight:600;}'
         'QPushButton:disabled{background:#2d2c33;color:#8e8e93;}')
DANGER=('QPushButton{color:#ff6961;font-weight:600;}'
        'QPushButton:disabled{color:#8e8e93;font-weight:400;}')


# Every Foldset window floats above Resolve's main window (Qt Tool panel): it hides while another
# app is active and returns when Resolve is active again. Normal windows were covered by the main
# window after an app switch. All windows share this, so dialogs never open behind a panel.
PANEL_FLAGS={'Tool':True,'WindowTitleHint':True,'WindowSystemMenuHint':True,'WindowCloseButtonHint':True}


def status_html(text,tone='info'):
    """One status line: coloured dot plus escaped text, so state never relies on colour alone."""
    return '<span style="color:%s">●</span>&nbsp; %s'%(TONES[tone],html.escape(text))


def wrap_path(path):
    """Escaped path that Qt rich text may break after each slash."""
    return html.escape(str(path)).replace('/','/\u200b')

_event_targets = {}


def run_window_events(ui,dispatcher,window_id,state,resolve=None,tick=None):
    """Keep nested windows responsive and retire the whole old-project session."""
    def project_id():
        project=resolve.GetProjectManager().GetCurrentProject()
        return project.GetUniqueId() if project else None
    origin=project_id() if resolve else None
    # A nested dialog belongs to the same session as its parent.
    if _event_targets:
        origin=next(iter(_event_targets.values()))['project']
    target={'dispatcher':dispatcher,'state':state,'project':origin}
    _event_targets[window_id]=target
    next_check=0
    try:
        while not state.get('closed'):
            if tick:tick()
            now=time.monotonic()
            if resolve and (next_check==0 or now>=next_check):
                next_check=now+0.25
                try:changed=project_id()!=origin
                except Exception:changed=True  # Project may be absent while switching.
                if changed:
                    for entry in _event_targets.values():entry['state']['close_requested']=True
            # Parent Close must unwind its active child instead of being discarded.
            closing=False
            for entry in _event_targets.values():
                current=entry['state']
                closing=closing or current.get('closed',False) or current.get('close_requested',False)
                if closing:current['close_requested']=True
                if current.get('close_requested') and (not current.get('working') or current.get('finished')):
                    current['closed']=True
            if state.get('closed'):break
            event=ui.GetEvent(False)
            if event:
                owner=_event_targets.get(event.get('window'))
                if owner and not owner['state'].get('closed'):
                    owner['dispatcher'].Dispatch(event)
            else:time.sleep(0.03)
    finally:
        _event_targets.pop(window_id,None)


def confirm(resolve,bmd,count,cleanup_pool=False):
    ui=resolve.Fusion().UIManager;dispatcher=bmd.UIDispatcher(ui)
    window_id='FoldsetTrashConfirm_'+uuid.uuid4().hex
    # The steps mirror foldset_browser.commit: strict rescan and project backup, trash, then pool removal.
    steps=(['先重新扫描全部时间线，确认这些文件仍未被使用；否则停止，不移动任何文件。',
            '导出当前项目备份（.drp）；备份失败则停止。',
            '把文件移到废纸篓。',
            '只移除已成功移入废纸篓的文件对应的媒体池条目。']
           if cleanup_pool else
           ['把文件移到废纸篓，不会永久删除。',
            '已导入达芬奇的素材会变成离线；其他项目也可能使用这些文件。'])
    undo=('Foldset 内无法撤销：文件请在 Finder 废纸篓中“放回原处”，媒体池需导入项目备份恢复。' if cleanup_pool
          else 'Foldset 内无法撤销：请在 Finder 废纸篓中“放回原处”。')
    body=('<ol>'+''.join('<li>%s</li>'%html.escape(s) for s in steps)+'</ol>'
          '<p style="color:#ff6961">%s</p>'%html.escape(undo))
    window=dispatcher.AddWindow({'ID':window_id,'WindowFlags':PANEL_FLAGS,'WindowTitle':'Foldset · 确认移到废纸篓','Geometry':{1:300,2:240,3:520,4:300 if cleanup_pool else 230}},ui.VGroup([
        ui.Label({'Text':status_html('将所选 %d 个文件移到废纸篓%s'%(count,'，并清理媒体池' if cleanup_pool else ''),'bad'),'Weight':0,'MinimumSize':[0,28]}),
        ui.Label({'Text':body,'WordWrap':True,'MinimumSize':[0,150 if cleanup_pool else 90]}),
        ui.HGroup({'Weight':0,1:ui.Label({'Text':'','Weight':1}),2:button(ui,'Cancel','取消'),3:button(ui,'Confirm','移到废纸篓')})]))
    window.GetItems()['Confirm'].StyleSheet=DANGER
    state={'confirmed':False,'closed':False}
    def accept(event):state['confirmed']=True;state['closed']=True
    window.On['Confirm'].Clicked=accept
    window.On['Cancel'].Clicked=lambda event:state.update(closed=True)
    window.On[window_id].Close=lambda event:state.update(closed=True)
    try:
        window.Show();window.Raise();window.ActivateWindow()
        run_window_events(ui,dispatcher,window_id,state,resolve)
    finally:window.Hide();window.ID='FoldsetTrashConfirmClosed'
    return state['confirmed'] and not state.get('close_requested')

def run_progress(resolve,bmd,total,task):
    ui=resolve.Fusion().UIManager;dispatcher=bmd.UIDispatcher(ui)
    window_id='FoldsetTrashProgress_'+uuid.uuid4().hex
    window=dispatcher.AddWindow({'ID':window_id,'WindowFlags':PANEL_FLAGS,'WindowTitle':'Foldset · 移到废纸篓','Geometry':{1:300,2:240,3:520,4:220},'MinimumSize':{1:520,2:220}},ui.VGroup([
        ui.Label({'ID':'Count','Text':'正在准备…','Weight':0,'MinimumSize':[0,28]}),
        ui.Label({'ID':'File','Text':'','Weight':0,'MinimumSize':{1:500,2:28},'MaximumSize':{1:500,2:28}}),
        ui.Label({'ID':'Bar','Text':'','TextFormat':'RichText','Weight':0,'MinimumSize':[0,18],'MaximumSize':[500,18]}),
        ui.Label({'ID':'Message','Text':'处理中，请勿断开素材磁盘。关闭窗口或切换项目会在当前文件完成后停止后续文件。','WordWrap':True,'MinimumSize':[0,48]}),
        button(ui,'Close','关闭')]))
    items=window.GetItems();items['Close'].Enabled=False
    state={'finished':False,'result':None,'error':None,'working':True}
    def update(event):
        done=event.get('done',0)
        items['Count'].Text='已移到废纸篓 %d / %d 个（%d%%）'%(done,total,100*done//max(total,1))
        name=Path(event.get('file','')).name
        items['File'].Text=name if len(name)<64 else name[:28]+'…'+name[-28:]
        items['File'].ToolTip=event.get('file','')
        width=max(1,480*done//max(total,1))
        items['Bar'].Text='<table cellspacing="0" cellpadding="0"><tr><td width="%d" bgcolor="#929ba8" height="8"></td><td width="%d" bgcolor="#171717"></td></tr></table>'%(width,max(1,480-width))
        if event.get('finished'):
            state['finished']=True;items['Close'].Enabled=True
            items['Message'].Text=event.get('message','处理完成。如需恢复，请在 Finder 废纸篓中“放回原处”。')
    events=queue.Queue()
    def publish(done,file=''):
        if file and state.get('close_requested'):
            raise RuntimeError('窗口已关闭或项目已切换，已停止后续文件操作。')
        state['done']=done
        events.put({'done':done,'file':file})
    def worker():
        done=0
        try:
            state['result']=task(publish)
            _,batch=state['result'];done=sum(e['state']=='trashed' for e in batch['entries'])
            errors=[e['error'] for e in batch['entries'] if e.get('error')]
            message=('已停止：'+errors[0]) if errors else '处理完成。如需恢复，请在 Finder 废纸篓中“放回原处”。'
        except Exception as error:
            state['error']=error;done=state.get('done',0);message='处理未完成：'+str(error)
        events.put({'done':done,'finished':True,'message':message})
    def close(event):
        if state['finished']:state['closed']=True
        else:state['close_requested']=True
    window.On['Close'].Clicked=close;window.On[window_id].Close=close
    try:
        window.Show();window.Raise();window.ActivateWindow()
        threading.Thread(target=worker,daemon=True).start()
        def tick():
            while not events.empty():update(events.get_nowait())
        run_window_events(ui,dispatcher,window_id,state,resolve,tick)
    finally:window.Hide();window.ID='FoldsetTrashProgressClosed'
    if state['error']:raise state['error']
    return state['result']


def show_legend(resolve,bmd):
    ui=resolve.Fusion().UIManager
    existing=ui.FindWindow('FoldsetTagLegend')
    if existing:
        existing.Show();existing.Raise();existing.ActivateWindow();return
    dispatcher=bmd.UIDispatcher(ui)
    def section(color,title,*lines):
        dot='<span style="color:%s">●</span>&nbsp; '%color if color else ''
        return '<p><b>%s%s</b><br>%s</p>'%(dot,title,'<br>'.join(lines))
    text=''.join([
        '<p style="color:#98989d">请以 Finder 中的完整标签名称为准，不要只看颜色。</p>',
        section(TONES['ok'],'绿色 · 已使用','在所选的当前／全部时间线范围内检测到了源文件引用。'),
        section(TONES['info'],'灰色 · 未使用候选','未检测到引用；不保证其他项目或被忽略的复合片段没有使用。'),
        section(TONES['warn'],'黄色 · 待核实','项目中有复合片段、Fusion 等无法完整读取的依赖，暂时无法确定是否使用。'),
        section(TONES['blue'],'蓝色 · 未导入当前项目','在所选磁盘文件夹中，但不在当前项目媒体池里。不等于可以删除。'),
        section(None,'紫色、红色、橙色及无颜色标签','Foldset 不用这些颜色表示使用状态。它们可能是手动设置、其他软件添加或文件原有的标签，含义取决于实际标签名称。'),
        section(None,'为什么同一文件有多个颜色？','Foldset 保留原有标签，也保留其他项目／扫描范围的 Foldset 标签。',
                '例如“紫色”加绿色“Foldset·…·已使用”：原紫色标签被保留，且本次检测到该文件已使用，并不是两个相互冲突的状态。'),
        section(None,'如何核对？','在 Finder 中右键文件 → 标签，查看完整标签名称。Foldset 标签包含项目标识、扫描范围和使用状态；同一颜色也可能属于其他自定义标签。'),
        '<p style="color:#98989d">标签是扫描时的快照，剪辑或文件位置变化后请重新扫描。未使用候选、未导入都不保证可以删除。</p>'])
    window=dispatcher.AddWindow({'ID':'FoldsetTagLegend','WindowFlags':PANEL_FLAGS,'WindowTitle':'Foldset · 标签说明',
        'Geometry':{1:260,2:160,3:560,4:590},'MinimumSize':{1:560,2:440}},ui.VGroup([
        ui.TextEdit({'ReadOnly':True,'HTML':text,'MinimumSize':{1:540,2:440}}),
        button(ui,'CloseLegend','关闭')]))
    state={'closed':False}
    def close(event):state['closed']=True
    window.On['CloseLegend'].Clicked=close;window.On['FoldsetTagLegend'].Close=close
    try:
        window.Show();window.Raise();window.ActivateWindow()
        run_window_events(ui,dispatcher,'FoldsetTagLegend',state,resolve)
    finally:window.Hide();window.ID='FoldsetTagLegendClosed'


def choose_exclusions(resolve,bmd,root,excluded):
    import os
    root=Path(root).expanduser().resolve()
    if not root.is_dir():raise ValueError('请先选择有效的素材文件夹。')
    folders=[]
    def walk_error(error):raise ValueError('无法读取子文件夹：'+str(error))
    for parent,dirs,_ in os.walk(root,followlinks=False,onerror=walk_error):
        dirs[:]=sorted(d for d in dirs if not d.startswith('.') and not Path(parent,d).is_symlink())
        folders.extend(str(Path(parent,d)) for d in dirs)
    ui=resolve.Fusion().UIManager;dispatcher=bmd.UIDispatcher(ui)
    window=dispatcher.AddWindow({'ID':'FoldsetExclusions','WindowFlags':PANEL_FLAGS,'WindowTitle':'Foldset · 排除文件夹','Geometry':{1:260,2:180,3:600,4:430},'MinimumSize':{1:540,2:340}},ui.VGroup([
        ui.Label({'Text':'选择不扫描的子文件夹，其下的子文件夹一并排除。按住 ⌘ 多选，Shift 连选。','WordWrap':True,'Weight':0}),
        ui.Label({'Text':'<span style="color:#98989d">素材文件夹：</span>'+wrap_path(root),'ToolTip':str(root),'WordWrap':True,'Weight':0}),
        ui.Tree({'ID':'Folders','ColumnCount':1,'RootIsDecorated':False,'SelectionMode':'ExtendedSelection','MinimumSize':{1:510,2:220}}),
        ui.Label({'Text':'<span style="color:#98989d">只影响扫描结果：不会移动文件、移除媒体池条目或清除已有标签。</span>','WordWrap':True,'Weight':0}),
        ui.HGroup({'Weight':0,1:button(ui,'Clear','取消全部排除'),2:ui.Label({'Text':'','Weight':1}),3:button(ui,'Cancel','取消'),4:button(ui,'Apply','应用排除')})]))
    window.GetItems()['Apply'].StyleSheet=PRIMARY
    tree=window.GetItems()['Folders'];header=tree.NewItem();header.Text[0]='子文件夹';tree.SetHeaderItem(header);tree.ColumnWidth[0]=550
    rows=[]
    for path in sorted(folders):
        row=tree.NewItem();row.Text[0]=str(Path(path).relative_to(root));row.ToolTip[0]=path;tree.AddTopLevelItem(row);row.Selected=path in excluded;rows.append((row,path))
    state={'result':None}
    def apply(event):state['result']=[p for r,p in rows if r.Selected];state.update(closed=True)
    def clear(event):
        for row,_ in rows:row.Selected=False
    window.On['Apply'].Clicked=apply;window.On['Clear'].Clicked=clear
    window.On['Cancel'].Clicked=lambda event:state.update(closed=True)
    window.On['FoldsetExclusions'].Close=lambda event:state.update(closed=True)
    try:window.Show();window.Raise();window.ActivateWindow();run_window_events(ui,dispatcher,'FoldsetExclusions',state,resolve)
    finally:window.Hide();window.ID='FoldsetExclusionsClosed'
    return state['result']


def reveal_menu(resolve,bmd,path,position):
    """Resolve-styled contextual popup; reveal only the clicked file."""
    import subprocess
    ui=resolve.Fusion().UIManager;dispatcher=bmd.UIDispatcher(ui)
    window_id='FoldsetRevealMenu_'+uuid.uuid4().hex
    x,y=position
    window=dispatcher.AddWindow({'ID':window_id,'WindowTitle':'在 Finder 中显示',
        'WindowFlags':{'Tool':True,'FramelessWindowHint':True,'WindowStaysOnTopHint':True},'Events':{'Close':True,'Hide':True,'KeyPress':True,'FocusOut':True},
        'Geometry':{1:x,2:y,3:190,4:48},'MinimumSize':{1:190,2:48}},ui.VGroup([
        ui.Button({'ID':'Reveal','Text':'在 Finder 中显示','ToolTip':path,'Flat':True,'MinimumSize':{1:170,2:28}})]))
    state={'closed':False}
    def reveal(event):
        if not Path(path).is_file():raise ValueError('文件不存在或磁盘未挂载：'+path)
        subprocess.run(['/usr/bin/open','-R',path],check=True)
        state['closed']=True
    def key(event):
        if event.get('Key')==16777216:state['closed']=True
    window.On[window_id].KeyPress=key
    window.On['Reveal'].Clicked=reveal
    window.On[window_id].FocusOut=lambda event:state.update(closed=True)
    window.On[window_id].Hide=lambda event:state.update(closed=True)
    window.On[window_id].Close=lambda event:state.update(closed=True)
    try:
        window.Show();window.Raise();window.ActivateWindow()
        run_window_events(ui,dispatcher,window_id,state,resolve)
    finally:window.Hide();window.ID='FoldsetRevealMenuClosed'
