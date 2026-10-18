import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Integrations/DaVinciResolve'))
import foldset_trash as trash
from foldset_usage import file_key

class TrashTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='foldset-trash-test-'))
        self.file=self.root/'clip.mov';self.file.write_text('fixture')
        self.records=[{'path':str(self.file),'identity':file_key(str(self.file))}]
    def test_changed_file_blocks_before_helper(self):
        batch=trash.plan(self.records);self.file.write_text('changed')
        with patch.object(trash.subprocess,'run') as run:
            with self.assertRaises(ValueError):trash.execute(batch,self.root/'logs')
            run.assert_not_called()
    def test_failure_never_deletes(self):
        with patch.object(trash.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout=b'',stderr=b'denied')):
            _,batch=trash.execute(trash.plan(self.records),self.root/'logs')
        self.assertTrue(self.file.exists());self.assertEqual(batch['entries'][0]['error'],'denied')
    def test_chinese_result_with_ascii_locale(self):
        import subprocess
        real_run=subprocess.run
        def native_result(command,**kwargs):
            self.assertNotIn('text',kwargs)
            self.assertNotIn('encoding',kwargs)
            payload='{"path":"/Volumes/A/.Trashes/501/中文素材.mov"}'.encode('utf-8')
            return real_run(['/usr/bin/python3','-c','import sys;sys.stdout.buffer.write('+repr(payload)+')'],**kwargs)
        with patch.object(trash.subprocess,'run',side_effect=native_result):
            _,batch=trash.execute(trash.plan(self.records),self.root/'logs')
        self.assertEqual(batch['entries'][0]['state'],'trashed')
        self.assertTrue(batch['entries'][0]['trashPath'].endswith('中文素材.mov'))

    def test_chinese_error_is_readable(self):
        import subprocess
        real_run=subprocess.run
        def native_error(command,**kwargs):
            payload='没有权限移到废纸篓'.encode('utf-8')
            return real_run(['/usr/bin/python3','-c','import sys;sys.stderr.buffer.write('+repr(payload)+');sys.exit(1)'],**kwargs)
        with patch.object(trash.subprocess,'run',side_effect=native_error):
            _,batch=trash.execute(trash.plan(self.records),self.root/'logs')
        self.assertEqual(batch['entries'][0]['error'],'没有权限移到废纸篓')
        self.assertTrue(self.file.exists())

    def test_records_system_result(self):
        updates=[]
        with patch.object(trash.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr=b'',stdout='{"path":"/fixture/.Trash/clip.mov"}')) as run:
            journal,batch=trash.execute(trash.plan(self.records),self.root/'logs',progress=lambda n,p: updates.append(n))
        self.assertEqual(batch['entries'][0]['state'],'trashed');self.assertTrue(journal.exists())
        self.assertEqual(run.call_args.args[0][1],str(self.file))
        self.assertEqual(updates,[0,1])

if __name__=='__main__':unittest.main()
