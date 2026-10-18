# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Integrations/DaVinciResolve'))
from foldset_bins import names_for, create_bins

class Bin:
    def __init__(self, name, children=None):
        self.name, self.children = name, children or []
    def GetName(self): return self.name
    def GetSubFolderList(self): return self.children

class Pool:
    def __init__(self, fail=None): self.fail, self.current = fail, None
    def AddSubFolder(self, parent, name):
        if name == self.fail: return None
        child = Bin(name)
        parent.children.append(child)
        self.current = child  # Resolve 21.1.1 switches the current bin to the new one.
        return child
    def GetCurrentFolder(self): return self.current
    def SetCurrentFolder(self, folder):
        self.current = folder
        return True

class Tests(unittest.TestCase):
    def test_names(self):
        t = dict(name='剪辑', start=1, digits=2, separator='_', numbered=True,
                 entries=[dict(name='视频素材'), dict(name=' 配音字幕 ')])
        self.assertEqual(names_for(t), ['01_视频素材', '02_配音字幕'])
        t['numbered'] = False
        self.assertEqual(names_for(t), ['视频素材', '配音字幕'])
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            names_for(dict(name='x', numbered=False, entries=[dict(name='a'),dict(name='A')]))
    def test_repeat_preserves(self):
        existing = Bin('素材')
        parent = Bin('Parent', [existing])
        pool = Pool()
        self.assertEqual(create_bins(pool, parent, ['素材','输出']), {'created':['输出'], 'skipped':['素材']})
        self.assertIs(parent.children[0], existing)
        self.assertEqual(create_bins(pool, parent, ['素材','输出'])['created'], [])
        self.assertEqual(len(parent.children), 2)
    def test_partial_failure(self):
        parent = Bin('Parent')
        with self.assertRaisesRegex(RuntimeError, '已创建 1 个'):
            create_bins(Pool('B'), parent, ['A','B','C'])
        self.assertEqual([b.name for b in parent.children], ['A'])
    def test_returns_to_target_bin(self):
        parent = Bin('Master')
        pool = Pool(); pool.current = parent
        create_bins(pool, parent, ['01_视频素材', '02_配音字幕'])
        self.assertIs(pool.current, parent)
    def test_returns_to_target_bin_after_failure(self):
        parent = Bin('Master')
        pool = Pool('B'); pool.current = parent
        with self.assertRaises(RuntimeError): create_bins(pool, parent, ['A', 'B'])
        self.assertIs(pool.current, parent)
    def test_no_target(self):
        with self.assertRaises(ValueError): create_bins(Pool(), None, ['A'])
    def test_no_mutation_on_duplicate(self):
        parent = Bin('Parent')
        with self.assertRaises(ValueError): create_bins(Pool(), parent, ['A','a'])
        self.assertEqual(parent.children, [])

class DirectEntryTests(unittest.TestCase):
    def test_direct_entry_never_opens_picker(self):
        from unittest.mock import MagicMock, patch
        import foldset_resolve
        resolve = MagicMock()
        project = resolve.GetProjectManager.return_value.GetCurrentProject.return_value
        project.GetUniqueId.return_value = 'project'
        parent = project.GetMediaPool.return_value.GetCurrentFolder.return_value
        parent.GetUniqueId.return_value = 'parent'
        template = dict(id='chosen', name='预设', numbered=False, entries=[dict(name='素材')])
        with patch.object(foldset_resolve, 'load_library', return_value={'templates': [template]}), \
             patch.object(foldset_resolve, 'show_window') as dialog, \
             patch.object(foldset_resolve, 'create_bins') as create:
            foldset_resolve.main(resolve, None, template_id='chosen')
            dialog.assert_not_called()
            self.assertEqual(create.call_args.args[2], ['素材'])

unittest.main()
