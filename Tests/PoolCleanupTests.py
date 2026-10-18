import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Integrations/DaVinciResolve'))
import foldset_pool_cleanup as c

class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.resolve=Mock();self.project=self.resolve.GetProjectManager().GetCurrentProject()
        self.project.GetUniqueId.return_value='project'
        self.clip=Mock();self.clip.GetName.return_value='clip.mov';self.clip.GetClipProperty.return_value={'Usage':'0'}
        self.batch={'projectID':'project','timelineState':[],'entries':[{'state':'trashed','mediaPoolIds':['one']},{'state':'planned','mediaPoolIds':['two']}]}
    def test_only_successful_files_removed(self):
        with patch.object(c,'timeline_state',return_value=[]),patch.object(c,'inventory',side_effect=[{'one':self.clip},{ }]),patch.object(c,'save_json'):
            count,errors=c.finish(self.resolve,self.batch,'unused.json')
        self.assertEqual(count,1);self.assertFalse(errors)
        self.project.GetMediaPool().DeleteClips.assert_called_once_with([self.clip])
    def test_new_usage_keeps_entry(self):
        self.clip.GetClipProperty.return_value={'Usage':'1'}
        with patch.object(c,'timeline_state',return_value=[]),patch.object(c,'inventory',return_value={'one':self.clip}),patch.object(c,'save_json'):
            count,errors=c.finish(self.resolve,self.batch,'unused.json')
        self.assertEqual(count,0);self.assertTrue(errors)
        self.project.GetMediaPool().DeleteClips.assert_not_called()
    def test_changed_timeline_keeps_entries(self):
        with patch.object(c,'timeline_state',return_value=['changed']):count,errors=c.finish(self.resolve,self.batch,'unused.json')
        self.assertEqual(count,0);self.assertTrue(errors)
        self.project.GetMediaPool().DeleteClips.assert_not_called()
    def test_unknown_dependency_blocks_before_backup(self):
        batch={'entries':[{'fingerprint':['key']} ]}
        with patch.object(c.usage,'scan',return_value={'records':[{'identity':'key','status':'unknown'}]}):
            with self.assertRaises(ValueError):c.prepare(self.resolve,batch)
        self.resolve.GetProjectManager().ExportProject.assert_not_called()

if __name__=='__main__':unittest.main()
