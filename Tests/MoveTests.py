import sys,tempfile,unittest,json,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Integrations/DaVinciResolve'))
import foldset_moves as m
from foldset_usage import file_key
from foldset_tags import read_tags,write_tags
class Tests(unittest.TestCase):
 def setUp(self):
  self.root=Path(tempfile.mkdtemp(prefix='Foldset-move-')).resolve();self.src=self.root/'src';self.dst=self.root/'dst';self.src.mkdir();self.dst.mkdir();self.logs=self.root/'logs'
 def file(self,name='clip.mov'):
  p=self.src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'media');return {'path':str(p),'identity':file_key(str(p))}
 def test_move_restore_preserves_data_tags(self):
  r=self.file();write_tags(r['path'],['客户\n6']);j,b=m.execute(m.plan([r],self.dst),self.logs)
  dest=self.dst/'clip.mov';self.assertFalse(Path(r['path']).exists());self.assertEqual(dest.read_bytes(),b'media');self.assertEqual(read_tags(str(dest)),['客户\n6'])
  self.assertEqual(m.latest_pending(self.logs),j);self.assertEqual(m.restore(j),(1,[]));self.assertIsNone(m.latest_pending(self.logs));self.assertEqual(Path(r['path']).read_bytes(),b'media')
 def test_chinese_journal_with_ascii_default(self):
  r=self.file('中文素材.mov');j,b=m.execute(m.plan([r],self.dst),self.logs)
  read_text=Path.read_text
  def ascii_default(path,encoding=None,errors=None,**kwargs):
   return read_text(path,encoding=encoding or 'ascii',errors=errors,**kwargs)
  with patch.object(Path,'read_text',ascii_default):
   self.assertEqual(m.latest_pending(self.logs),j)
   self.assertEqual(m.restore(j),(1,[]))
   self.assertIsNone(m.latest_pending(self.logs))
  self.assertEqual(Path(r['path']).read_bytes(),b'media')
 def test_conflict_preflight_no_move(self):
  a=self.file('a.mov');b=self.file('b.mov');(self.dst/'b.mov').write_bytes(b'existing')
  with self.assertRaises(ValueError):m.plan([a,b],self.dst)
  self.assertTrue(Path(a['path']).exists())
 def test_source_modified_after_preview(self):
  a=self.file();plan=m.plan([a],self.dst);Path(a['path']).write_bytes(b'changed')
  with self.assertRaises(ValueError):m.execute(plan,self.logs)
 def test_exclusive_rename_never_overwrites(self):
  a=self.file();d=self.dst/'clip.mov';d.write_bytes(b'keep')
  with self.assertRaises(OSError):m.rename_exclusive(a['path'],d)
  self.assertEqual(d.read_bytes(),b'keep');self.assertTrue(Path(a['path']).exists())
 def test_restore_conflict_preserves_both(self):
  a=self.file();j,b=m.execute(m.plan([a],self.dst),self.logs);Path(a['path']).write_bytes(b'new')
  n,err=m.restore(j);self.assertEqual(n,0);self.assertTrue(err);self.assertEqual(Path(a['path']).read_bytes(),b'new');self.assertTrue((self.dst/'clip.mov').exists())
 def test_restore_modified_destination_skipped(self):
  a=self.file();j,b=m.execute(m.plan([a],self.dst),self.logs);(self.dst/'clip.mov').write_bytes(b'edited')
  self.assertEqual(m.restore(j)[0],0)
 def test_relative_directories(self):
  a=self.file('a/clip.mov');b=self.file('b/clip.mov');j,result=m.execute(m.plan([a,b],self.dst),self.logs)
  self.assertTrue((self.dst/'a/clip.mov').exists());self.assertTrue((self.dst/'b/clip.mov').exists());self.assertEqual(m.restore(j),(2,[]))
 def test_partial_failure_is_recoverable(self):
  a=self.file('a.mov');b=self.file('b.mov');real=m.rename_exclusive
  with patch.object(m,'rename_exclusive',side_effect=[None,OSError('blocked')]):
   # Simulate the first rename while the second fails.
   def move(src,dst):
    if str(src).endswith('b.mov'):raise OSError('blocked')
    real(src,dst)
   with patch.object(m,'rename_exclusive',side_effect=move):j,result=m.execute(m.plan([a,b],self.dst),self.logs)
  self.assertEqual(result['entries'][0]['state'],'moved');self.assertIn('error',result['entries'][1]);self.assertEqual(m.restore(j),(1,[]))
 def test_crash_between_move_and_journal_update(self):
  a=self.file();plan=m.plan([a],self.dst);self.logs.mkdir();j=self.logs/'crash.json';m.save_json(j,plan);m.rename_exclusive(a['path'],plan['entries'][0]['destination'])
  self.assertEqual(m.latest_pending(self.logs),j);self.assertEqual(m.restore(j),(1,[]))
 def test_symlink_source_rejected(self):
  a=self.file();p=self.src/'link.mov';p.symlink_to(a['path'])
  with self.assertRaises(ValueError):m.plan([{'path':str(p),'identity':a['identity']}],self.dst)
unittest.main()
