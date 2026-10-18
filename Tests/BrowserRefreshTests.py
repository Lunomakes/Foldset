"""A completed trash operation must not blank unrelated categories."""
import sys
import tempfile
import unittest
from pathlib import Path
from collections import defaultdict
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Integrations/DaVinciResolve'))
import foldset_browser as browser

class RefreshTests(unittest.TestCase):
    def exercise(self, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'used.mov';source.touch()
            used={'path':str(source),'status':'used'}
            unused={'path':str(Path(directory)/'unused.mov'),'status':'unused'}
            before={'project':'test','projectID':'p','scope':'all','signature':'a','records':[used,unused]}
            after={**before,'signature':'b','records':[used]}
            resolve,bmd=MagicMock(),MagicMock()
            resolve.Fusion.return_value.UIManager.FindWindow.return_value=None
            window=bmd.UIDispatcher.return_value.AddWindow.return_value
            items=defaultdict(MagicMock);events=defaultdict(MagicMock)
            window.GetItems.return_value=items;window.On=events
            items['Files'].NewItem.side_effect=lambda:MagicMock()
            def interact(*args):
                attrs=bmd.UIDispatcher.return_value.AddWindow.call_args.args[0]
                self.assertTrue(attrs['Events']['Close'])
                events['used'].Clicked(None)
                clicked=MagicMock();clicked.ToolTip={0:str(source)}
                items['Files'].ItemAt.return_value=clicked
                with patch.object(browser.dialogs,'reveal_menu') as reveal:
                    point={'X':20,'Y':10}
                    events['Files'].ContextMenu({'Pos':point,'GlobalPos':{'X':300,'Y':200}})
                    items['Files'].ItemAt.assert_called_once_with(point)
                    reveal.assert_called_once_with(resolve,bmd,str(source),(300,200))
                    reveal.reset_mock();items['Files'].ItemAt.reset_mock()
                    with patch.object(browser.time,'monotonic',return_value=1000000):
                        events['Files'].ItemPressed({'Item':clicked})
                        events['FoldsetMediaBrowserR2'].ContextMenu({'Pos':point,'GlobalPos':{'X':300,'Y':200}})
                    items['Files'].ItemAt.assert_not_called()
                    reveal.assert_called_once_with(resolve,bmd,str(source),(300,200))
                events['unused'].Clicked(None)
                events['All'].Clicked(None)
                events['Trash'].Clicked(None)
                events['used'].Clicked(None)
                self.assertEqual(items['Count'].Text,'显示 1 个 · 已选 1 个')
                self.assertEqual(items['used'].Text,'● 已使用 1')
                self.assertEqual(items['unused'].Text,'未使用候选 0')
                self.assertEqual(items['Trash'].Enabled,not fail)
                self.assertIn('刷新失败' if fail else '列表已更新',items['Preview'].Text)
                events['FoldsetMediaBrowserR2'].Close({})
                window.Hide.assert_called_once()



            with patch.object(browser.dialogs,'run_window_events',side_effect=interact),patch.object(browser.usage,'scan',side_effect=[before,RuntimeError('scan failed') if fail else after]),patch.object(browser.trash,'plan',return_value={'entries':[{'state':'planned'}]}),patch.object(browser.dialogs,'confirm',return_value=True),patch.object(browser.dialogs,'run_progress',return_value=('journal',{'entries':[{'state':'trashed'}]})),patch.object(browser.cleanup,'prepare'),patch.object(browser.cleanup,'finish',return_value=(1,[])),patch.object(browser.moves,'latest_pending',return_value=None):
                browser.open_window(resolve,bmd,before,MagicMock())
    def test_trash_refresh_keeps_other_categories(self):self.exercise()
    def test_failed_refresh_keeps_existing_files_read_only(self):self.exercise(True)

if __name__=='__main__':unittest.main()
