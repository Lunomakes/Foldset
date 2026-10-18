# -*- coding: utf-8 -*-
"""Index-free scan results browser with explicit move preview and recovery."""
from pathlib import Path
import time
import foldset_moves as moves
import foldset_usage as usage
import foldset_trash as trash
import foldset_dialogs as dialogs
import foldset_pool_cleanup as cleanup

KINDS = [('used','已使用'),('unused','未使用候选'),('not_imported','未导入'),('unknown','待核实')]
# What each category means here, and what it does not promise.
MEANING = {'used':('ok','绿色标签 · 所选范围内确认使用。'),
           'unused':('info','灰色标签 · 所选范围内未发现使用。不等于可以删除：其他项目或被忽略的复合片段仍可能使用。'),
           'not_imported':('blue','蓝色标签 · 在对比文件夹中，但不在当前媒体池。不等于可以删除。'),
           'unknown':('warn','黄色标签 · 项目中有无法确认的依赖，整体保守处理；原因见使用状态窗口的说明。')}


def open_window(resolve,bmd,report,invalidate):
    ui=resolve.Fusion().UIManager
    existing=ui.FindWindow('FoldsetMediaBrowserR2')
    if existing:
        existing.Show();existing.Raise();existing.ActivateWindow()
        return
    dispatcher=bmd.UIDispatcher(ui)
    def button(id,text,width):
        return ui.Button({'ID':id,'Text':text,'Weight':0,'MinimumSize':[width,28],'MaximumSize':[width,28]})
    window=dispatcher.AddWindow({'ID':'FoldsetMediaBrowserR2','WindowFlags':dialogs.PANEL_FLAGS,'WindowTitle':'Foldset · 素材列表','Events':{'Close':True,'ContextMenu':True},'Geometry':{1:180,2:120,3:656,4:600},'MinimumSize':{1:520,2:560}},ui.VGroup([
        ui.HGroup({'Weight':0,**{i+1:button(k,title+' %d'%sum(r['status']==k for r in report['records']),114) for i,(k,title) in enumerate(KINDS)}}),
        # Width caps as in the original layout; uncapped labels were laid out wider than the window.
        ui.Label({'ID':'KindInfo','Text':'','WordWrap':True,'Weight':0,'MinimumSize':[0,40],'MaximumSize':[480,60]}),
        ui.HGroup({'Weight':0,1:ui.Label({'Text':'文件夹','Weight':0}),2:ui.ComboBox({'ID':'Folder','MaximumSize':[400,28]})}),
        ui.Tree({'ID':'Files','Events':{'ItemSelectionChanged':True,'ItemClicked':True,'CurrentItemChanged':True,'ContextMenu':True,'MouseRelease':True,'ItemPressed':True},'ContextMenuPolicy':'DefaultContextMenu','ColumnCount':2,'RootIsDecorated':False,'AlternatingRowColors':True,'SelectionMode':'ExtendedSelection','MinimumSize':[0,220],'MaximumSize':[560,10000]}),
        ui.Label({'ID':'Count','Text':'','Weight':0}),
        ui.HGroup({'Weight':0,1:button('All','全选',70),2:button('None','取消选择',88),3:button('Prepare','移动所选文件到…',154),4:button('Trash','移到废纸篓…',132)}),
        ui.Label({'ID':'Preview','Text':'选择分类和文件，再选择移动或移到废纸篓。列表来自本次扫描，不依赖 Finder 搜索索引。','WordWrap':True,'MinimumSize':{1:0,2:64},'MaximumSize':{1:10000,2:100},'Weight':0}),
        ui.HGroup({'Weight':0,1:button('Commit','确认移动',154),2:button('Cancel','取消操作',104),3:button('Restore','恢复上次移动',132),4:button('Legend','标签说明…',100)}),
        ui.Label({'Text':'<span style="color:#98989d">移动：只在同一磁盘内，不覆盖已有文件，可恢复上次移动；已导入素材移动后会在达芬奇中离线，Foldset 不会自动重新链接。<br>'
                         '废纸篓：不会永久删除，但 Foldset 内无法撤销，需在 Finder 废纸篓中“放回原处”。</span>','WordWrap':True,'Weight':0,'MaximumSize':[480,80]})]))
    items=window.GetItems();tree=items['Files']
    header=tree.NewItem();header.Text[0]='文件名';header.Text[1]='所在文件夹';tree.SetHeaderItem(header)
    tree.ColumnWidth[0]=260;tree.ColumnWidth[1]=260
    initial_folder=report.get('diskFolder')
    initial_folder=str(Path(initial_folder)) if initial_folder else None
    folders=sorted({str(Path(r['path']).parent) for r in report['records']} | ({initial_folder} if initial_folder else set()))
    items['Folder'].AddItem('全部文件夹')
    for folder in folders: items['Folder'].AddItem(folder)
    items['Folder'].CurrentIndex=folders.index(initial_folder)+1 if initial_folder else 0
    state={'kind':'not_imported','rows':[],'plan':None,'valid':True,'choosing':False,'rendering':False}
    items['Commit'].Enabled=False;items['Cancel'].Enabled=False
    items['Commit'].StyleSheet=dialogs.PRIMARY;items['Trash'].StyleSheet=dialogs.DANGER
    def cancel(event=None):
        state['plan']=None;items['Commit'].Enabled=False;items['Cancel'].Enabled=False
        items['Commit'].Text='确认移动'
    def selected():
        return [record for row,record in state['rows'] if row.Selected]
    def count(event=None):
        if state['rendering']: return
        cancel()
        items['Count'].Text='显示 %d 个 · 已选 %d 个'%(len(state['rows']),len(selected()))
        items['Prepare'].Enabled=state['valid'] and bool(selected())
        items['Trash'].Enabled=items['Prepare'].Enabled
    def render(event=None):
        state['rendering']=True;tree.Clear();state['rows']=[]
        parent=folders[items['Folder'].CurrentIndex-1] if items['Folder'].CurrentIndex>0 else None
        scoped=[r for r in report['records'] if (state['valid'] or Path(r['path']).is_file()) and (not parent or Path(r['path']).is_relative_to(Path(parent)))]
        items['Folder'].ToolTip=parent or '全部扫描结果中的文件夹'
        for record in scoped:
            if record['status']!=state['kind']:continue
            row=tree.NewItem();row.Text[0]=Path(record['path']).name;row.Text[1]='/'.join(Path(record['path']).parent.parts[-2:])
            row.ToolTip[0]=record['path'];row.ToolTip[1]=record['path'];tree.AddTopLevelItem(row)
            state['rows'].append((row,record))
        for key,title in KINDS:
            items[key].Text=('● ' if key==state['kind'] else '')+title+' %d'%sum(r['status']==key for r in scoped)
            items[key].StyleSheet=dialogs.PRIMARY if key==state['kind'] else ''
        tone,meaning=MEANING[state['kind']]
        items['KindInfo'].Text=dialogs.status_html(meaning,tone)
        state['rendering']=False;count()
        items['Restore'].Enabled=bool(moves.latest_pending())
    def rescan():
        return usage.scan(resolve.GetProjectManager().GetCurrentProject(),report['scope'],
            ignore_compounds=report.get('ignoreCompounds',False),disk_folder=report.get('diskFolder'),excluded_folders=report.get('excludedFolders',[]))
    def refresh_after_change():
        nonlocal report
        state['valid']=False
        invalidate()
        try:
            fresh=rescan()
            if fresh['projectID']!=report['projectID']:
                raise ValueError('当前项目已切换')
            report=fresh
            state['valid']=True
            items['Preview'].Text+='\n列表已更新。'
        except Exception as error:
            items['Preview'].Text+='\n刷新失败，当前仅供查看，请重新扫描：'+str(error)
        render()
    def choose_kind(kind):
        def callback(event):state['kind']=kind;render()
        return callback
    def select_all(value):
        def callback(event):
            state['rendering']=True
            for row,_ in state['rows']:row.Selected=value
            state['rendering']=False;count()
        return callback
    def prepare(event):
        cancel();records=selected()
        if not records:return
        state['choosing']=True
        try:
            destination=resolve.Fusion().RequestDir(str(Path(records[0]['path']).parent))
            if destination:
                state['plan']=moves.plan(records,destination)
                state['plan']['project']=report['project']
                items['Preview'].Text=('将移动 %d 个文件到：\n%s\n· 保留所选文件之间的相对目录结构；遇到同名文件会停止，不覆盖。'
                    '\n· 已导入素材移动后会在达芬奇中离线。\n· 之后可用“恢复上次移动”撤回。点击“确认移动”执行。')%(len(records),destination)
                items['Commit'].Enabled=True;items['Cancel'].Enabled=True
        except Exception as error:items['Preview'].Text=str(error)
        finally:
            state['choosing']=False;window.Show();window.Raise();window.ActivateWindow()
    def prepare_trash(event):
        cancel()
        try:
            batch=trash.plan(selected());batch['action']='trash';batch['project']=report['project']
            batch['cleanupPool']=state['kind']=='unused'
            state['choosing']=True
            if dialogs.confirm(resolve,bmd,len(batch['entries']),cleanup_pool=batch['cleanupPool']):
                state['plan']=batch
                commit(event)
        except Exception as error:items['Preview'].Text=str(error)
        finally:
            state['choosing']=False;window.Enabled=True
            window.Raise();window.ActivateWindow()
    def commit(event):
        batch=state['plan']
        if not batch:return
        cancel()
        changed=False
        try:
            fresh=rescan()
            if fresh['signature']!=report['signature']:
                raise ValueError('项目或文件状态已改变，请回到使用状态窗口重新扫描并打开列表。')
            if batch.get('action')=='trash':
                if batch.get('cleanupPool'):cleanup.prepare(resolve,batch)
                try:
                    journal,result=dialogs.run_progress(resolve,bmd,len(batch['entries']),lambda update:trash.execute(batch,progress=update))
                finally:
                    changed=True
                pool_message=''
                if batch.get('cleanupPool'):
                    removed,pool_errors=cleanup.finish(resolve,result,journal)
                    pool_message='\n媒体池已移除 %d 项。'%removed+('\n'+pool_errors[0] if pool_errors else '')
                done=sum(e['state']=='trashed' for e in result['entries'])
                errors=[e['error'] for e in result['entries'] if e.get('error')]
                items['Preview'].Text='已移到废纸篓 %d / %d 个。\nFoldset 内无法撤销；如需恢复，请在 Finder 废纸篓中“放回原处”。%s'%(done,len(result['entries']),('\n'+errors[0]) if errors else '')+pool_message
                return
            changed=True
            journal,result=moves.execute(batch)
            done=sum(e['state']=='moved' for e in result['entries'])
            errors=[e.get('error') for e in result['entries'] if e.get('error')]
            items['Preview'].Text='已移动 %d / %d 个。如需撤回，点击“恢复上次移动”。\n记录：%s%s'%(done,len(result['entries']),journal,('\n'+errors[0]) if errors else '')
        except Exception as error:items['Preview'].Text=('未完成，没有继续处理后续文件：' if changed else '未执行：')+str(error)
        finally:
            if changed:refresh_after_change()
    def restore(event):
        changed=False
        try:
            journal=moves.latest_pending()
            if not journal:return
            changed=True
            n,errors=moves.restore(journal)
            items['Preview'].Text='已恢复 %d 个；跳过 %d 个。'%(n,len(errors))+ ('\n'+errors[0] if errors else '')
        except Exception as error:items['Preview'].Text='恢复未完成：'+str(error)
        finally:
            if changed:refresh_after_change()
    def context_menu(event):
        if state['choosing'] or ('last_menu' in state and time.monotonic()-state['last_menu']<0.4):return
        try:
            pos=event.get('Pos',{})
            if event.get('_parent') and event.get('GlobalPos'):
                pos=tree.MapFromGlobal(event['GlobalPos'])
            def xy(value):
                if isinstance(value,dict):return (value.get('X',value.get('x',value.get(1,0))),value.get('Y',value.get('y',value.get(2,0))))
                return value[0],value[1]
            x,y=xy(pos)
            pressed=state.pop('pressed_row',None)
            row=event.get('Item')
            if row is None and pressed and time.monotonic()-pressed[1]<1:
                row=pressed[0]
            if row is None:row=tree.ItemAt(pos)
            if not row:return
            # The tooltip is the canonical path bound when constructing this row.
            path=row.ToolTip[0]
            if not any(r['path']==path for _,r in state['rows']):return
            state['choosing']=True
            dialogs.reveal_menu(resolve,bmd,path,xy(event.get('GlobalPos',pos)))
        except Exception as error:items['Preview'].Text='无法在 Finder 显示：'+str(error)
        finally:
            state['choosing']=False;state['last_menu']=time.monotonic()
            window.Raise();window.ActivateWindow()
    def mouse_menu(event):
        if event.get('Button') in (2,'RightButton','Right') or event.get('Buttons')==2:context_menu(event)
    def item_pressed(event):
        # Resolve supplies the actual row here; window coordinates include the header.
        state['pressed_row']=(event.get('Item'),time.monotonic())
    def parent_menu(event):context_menu(dict(event,_parent=True))
    def legend(event):
        window.Enabled=False
        try:dialogs.show_legend(resolve,bmd)
        finally:window.Enabled=True;window.Raise();window.ActivateWindow()
    window.On['Files'].ContextMenu=context_menu
    window.On['Files'].MouseRelease=mouse_menu
    window.On['Files'].ItemPressed=item_pressed
    window.On['FoldsetMediaBrowserR2'].ContextMenu=parent_menu
    window.On['Legend'].Clicked=legend
    for key,title in KINDS:window.On[key].Clicked=choose_kind(key)
    window.On['Folder'].CurrentIndexChanged=render
    window.On['Files'].ItemSelectionChanged=count
    window.On['Files'].ItemClicked=count
    window.On['Files'].CurrentItemChanged=count
    window.On['All'].Clicked=select_all(True);window.On['None'].Clicked=select_all(False)
    window.On['Trash'].Clicked=prepare_trash
    window.On['Prepare'].Clicked=prepare;window.On['Commit'].Clicked=commit
    window.On['Cancel'].Clicked=cancel;window.On['Restore'].Clicked=restore
    def close(event):
        state['closed']=True
        window.Hide()
    window.On['FoldsetMediaBrowserR2'].Close=close
    render()
    try:window.Show();window.Raise();window.ActivateWindow();dialogs.run_window_events(ui,dispatcher,'FoldsetMediaBrowserR2',state,resolve)
    finally:
        window.Hide()
        window.ID='FoldsetMediaBrowserR2Closed'
