# -*- coding: utf-8 -*-
"""Resolve menu entry points using Resolve's own UI Manager."""
import html
from foldset_bins import load_library, names_for, create_bins

# Kept local: preset menu scripts reload only foldset_bins and this module, so a cached
# foldset_dialogs could be an older version without these names.
_PRIMARY = ('QPushButton{background:#f2f2f3;color:#111112;border-radius:14px;font-weight:600;}'
            'QPushButton:disabled{background:#2d2c33;color:#8e8e93;}')


def _status(text, color):
    return '<span style="color:%s">●</span>&nbsp; %s' % (color, html.escape(text).replace('\n', '<br>'))


def show_window(resolve, bmd, title, message, templates=None):
    ui = resolve.Fusion().UIManager
    dispatcher = bmd.UIDispatcher(ui)
    # Templates present = choosing; absent = reporting an error.
    rows = [ui.Label({'Text': _status(message, '#98989d' if templates else '#ff6961'), 'WordWrap': True})]
    if templates:
        rows.append(ui.ComboBox({'ID': 'Template', 'Weight': 0}))
    rows.append(ui.HGroup({
        'Weight': 0,
        1: ui.Label({'Text': '', 'Weight': 1}),
        2: ui.Button({'ID': 'Cancel', 'Text': '取消' if templates else '关闭',
                      'Weight': 0, 'MinimumSize': [80, 28], 'MaximumSize': [80, 28]}),
        3: ui.Button({'ID': 'Create', 'Text': '创建', 'Hidden': not bool(templates),
                      'Weight': 0, 'MinimumSize': [80, 28], 'MaximumSize': [80, 28]})}))
    # Same floating panel as the other Foldset windows (see foldset_dialogs.PANEL_FLAGS), kept local
    # because preset menus do not reload foldset_dialogs.
    window = dispatcher.AddWindow({'ID': 'FoldsetBinsCompact', 'WindowTitle': title,
                                   'WindowFlags': {'Tool': True, 'WindowTitleHint': True,
                                                   'WindowSystemMenuHint': True, 'WindowCloseButtonHint': True},
                                   'Geometry': [100, 100, 440, 180], 'MinimumSize': [360, 180]}, ui.VGroup(rows))
    items = window.GetItems()
    items['Create'].StyleSheet = _PRIMARY
    if templates:
        for template in templates:
            items['Template'].AddItem(template['name'])
    answer = []
    def close(event): dispatcher.ExitLoop()
    def create(event):
        answer.append(items['Template'].CurrentIndex)
        dispatcher.ExitLoop()
    window.On['FoldsetBinsCompact'].Close = close
    window.On['Cancel'].Clicked = close
    window.On['Create'].Clicked = create
    window.Show()
    window.Geometry = [100, 100, 440, 180]
    dispatcher.RunLoop()
    window.Hide()
    return answer[0] if answer else None


def main(resolve, bmd, use_default=False, template_id=None):
    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        if not project:
            raise ValueError('请先在达芬奇中打开一个项目。')
        pool = project.GetMediaPool()
        parent = pool.GetCurrentFolder()
        if not parent:
            raise ValueError('请先选中一个普通媒体夹。')
        project_id, parent_id = project.GetUniqueId(), parent.GetUniqueId()
        library = load_library()
        templates = library['templates']
        if template_id is not None:
            template = next((t for t in templates if t["id"] == template_id), None)
            if template is None:
                raise ValueError("此预设已删除，请打开 Foldset 刷新菜单。")
        elif use_default:
            template = next((t for t in templates if t['id'] == library.get('defaultID')), None)
            if template is None:
                raise ValueError('请先在 Foldset 中设置默认模板。')
        else:
            message = ('将在项目「%s」的媒体夹「%s」中创建子媒体夹。\n已有同名媒体夹会跳过，不会改名、移动或删除现有内容。'
                       % (project.GetName(), parent.GetName()))
            index = show_window(resolve, bmd, 'Foldset · 创建媒体夹', message, templates)
            if index is None:
                return
            template = templates[index]
        names = names_for(template)
        current = resolve.GetProjectManager().GetCurrentProject()
        if not current or current.GetUniqueId() != project_id:
            raise ValueError('当前项目已切换，请重新调用 Foldset。')
        if pool.GetCurrentFolder().GetUniqueId() != parent_id:
            raise ValueError('选中的媒体夹已改变，请重新调用 Foldset。')
        create_bins(pool, parent, names)
    except Exception as error:
        show_window(resolve, bmd, 'Foldset · 无法创建媒体夹', str(error))
