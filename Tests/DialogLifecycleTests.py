import sys,unittest
from pathlib import Path
from collections import defaultdict
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Integrations/DaVinciResolve'))
import foldset_dialogs as dialogs

class LifecycleTests(unittest.TestCase):
    def test_parent_ignores_retired_child_events(self):
        ui,dispatcher=MagicMock(),MagicMock();state={'closed':False}
        ui.GetEvent.side_effect=[{'window':'old-menu','event':'Hide'},
                                 {'window':'parent','event':'Close'}]
        dispatcher.Dispatch.side_effect=lambda event:state.update(closed=True)
        dialogs.run_window_events(ui,dispatcher,'parent',state)
        dispatcher.Dispatch.assert_called_once_with({'window':'parent','event':'Close'})

    def test_switch_project_closes_idle_window(self):
        ui,dispatcher,resolve=MagicMock(),MagicMock(),MagicMock()
        project=resolve.GetProjectManager.return_value.GetCurrentProject.return_value
        project.GetUniqueId.side_effect=['A','B']
        state={}
        dialogs.run_window_events(ui,dispatcher,'parent',state,resolve)
        self.assertTrue(state['closed'])
        ui.GetEvent.assert_not_called()
        self.assertFalse(dialogs._event_targets)

    def test_child_routes_parent_close_and_unwinds(self):
        ui,parent,child=MagicMock(),MagicMock(),MagicMock()
        outer,inner={},{}
        ui.GetEvent.side_effect=[{'window':'parent','event':'OpenChild'},
                                 {'window':'parent','event':'Close'}]
        def dispatch(event):
            if event['event']=='OpenChild':
                dialogs.run_window_events(ui,child,'child',inner)
            else:outer['closed']=True
        parent.Dispatch.side_effect=dispatch
        dialogs.run_window_events(ui,parent,'parent',outer)
        self.assertTrue(inner['closed'])
        self.assertTrue(inner['close_requested'])
        self.assertEqual(parent.Dispatch.call_count,2)
        child.Dispatch.assert_not_called()
        self.assertFalse(dialogs._event_targets)

    def test_switch_waits_for_active_file_to_finish(self):
        ui,dispatcher,resolve=MagicMock(),MagicMock(),MagicMock()
        project=resolve.GetProjectManager.return_value.GetCurrentProject.return_value
        project.GetUniqueId.side_effect=['A','B']
        state={'working':True,'finished':False}
        ui.GetEvent.return_value=None
        def tick():
            if state.get('close_requested'):state['finished']=True
        dialogs.run_window_events(ui,dispatcher,'progress',state,resolve,tick)
        self.assertTrue(state['finished'])
        self.assertTrue(state['closed'])

    def test_previous_close_does_not_cancel_first_confirmation(self):
        resolve,bmd=MagicMock(),MagicMock()
        ui=resolve.Fusion.return_value.UIManager
        dispatcher=bmd.UIDispatcher.return_value
        root=dispatcher.AddWindow.return_value
        root.On=defaultdict(MagicMock)
        ids=[]
        def add(attrs,layout):
            ids.append(attrs['ID'])
            ui.GetEvent.side_effect=[{'window':'FoldsetTrashConfirmClosed','event':'Close'},
                                    {'window':attrs['ID'],'event':'Confirm'}]
            return root
        dispatcher.AddWindow.side_effect=add
        dispatcher.Dispatch.side_effect=lambda e:root.On['Confirm'].Clicked(e)
        self.assertTrue(dialogs.confirm(resolve,bmd,1))
        self.assertTrue(dialogs.confirm(resolve,bmd,1))
        self.assertNotEqual(ids[0],ids[1])
        self.assertEqual(dispatcher.Dispatch.call_count,2)
        dispatcher.RunLoop.assert_not_called()
        dispatcher.ExitLoop.assert_not_called()

if __name__=='__main__':unittest.main()
