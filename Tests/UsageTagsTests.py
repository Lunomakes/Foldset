# -*- coding: utf-8 -*-
import errno
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Integrations/DaVinciResolve'))
import foldset_usage as usage
import foldset_tags as tags

class Tests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='Foldset-usage-test-')).resolve()
        self.a=self.root/'used.mov';self.a.write_bytes(b'test-media-content')
        self.b=self.root/'unused.wav';self.b.write_bytes(b'test-media-content')
        self.project=MagicMock()
        self.project.GetName.return_value='测试项目'
        self.project.GetUniqueId.return_value='project-test'
        self.pool=self.project.GetMediaPool.return_value
        folder=self.pool.GetRootFolder.return_value
        folder.GetSubFolderList.return_value=[]
        self.ca=self.clip('a',self.a,'0')
        self.cb=self.clip('b',self.b,'0')
        folder.GetClipList.return_value=[self.ca,self.cb]
        self.pool.GetClipMatteList.return_value=[]
        self.timeline=MagicMock()
        self.timeline.GetUniqueId.return_value='timeline'
        self.timeline.GetName.return_value='测试时间线'
        self.timeline.GetTrackCount.side_effect=lambda k: 1 if k=='video' else 0
        self.item=MagicMock()
        self.item.GetName.return_value="测试片段"
        self.item.GetMediaPoolItem.return_value=self.ca
        self.item.GetFusionCompCount.return_value=0
        self.item.GetTakesCount.return_value=0
        self.timeline.GetItemListInTrack.return_value=[self.item]
        self.project.GetCurrentTimeline.return_value=self.timeline
        self.project.GetTimelineCount.return_value=1
        self.project.GetTimelineByIndex.return_value=self.timeline
    def clip(self,id,path,usage_value):
        clip=MagicMock()
        clip.GetUniqueId.return_value=id
        clip.GetName.return_value=id
        clip.GetClipProperty.return_value={'File Path':str(path) if path else '', 'Usage':usage_value}
        clip.GetTimeline.return_value=None
        return clip
    def test_zero_usage_does_not_override_timeline(self):
        r=usage.scan(self.project)
        self.assertEqual({Path(x['path']).name:x['status'] for x in r['records']},{'used.mov':'used','unused.wav':'unused'})
    def test_unresolved_compound_blocks_unused(self):
        self.item.GetMediaPoolItem.return_value=self.clip('compound',None,'1')
        r=usage.scan(self.project)
        self.assertTrue(all(x['status']=='unknown' for x in r['records']))
        self.assertTrue(r['blockers'])
    def test_ignore_compound_is_explicit_and_audited(self):
        self.item.GetMediaPoolItem.return_value=self.clip('compound',None,'1')
        strict=usage.scan(self.project)
        relaxed=usage.scan(self.project,ignore_compounds=True)
        self.assertTrue(all(r['status']=='unused' for r in relaxed['records']))
        self.assertTrue(relaxed['ignoredDependencies'])
        self.assertNotEqual(strict['signature'],relaxed['signature'])
        self.assertIn('可能仍被其内部使用',usage.summary(relaxed))
    def test_ignore_compound_keeps_fusion_protection(self):
        self.item.GetMediaPoolItem.return_value=self.clip('compound',None,'1')
        self.item.GetFusionCompCount.return_value=1
        r=usage.scan(self.project,ignore_compounds=True)
        self.assertTrue(all(x['status']=='unknown' for x in r['records']))
        self.assertEqual(len(r['blockers']),1)
    def test_scope_current_ignores_other_timeline_usage(self):
        self.cb.GetClipProperty.return_value['Usage']='2'
        all_report=usage.scan(self.project,'all')
        current_report=usage.scan(self.project,'current')
        self.assertEqual(next(r for r in all_report['records'] if r['path']==str(self.b))['status'],'used')
        self.assertEqual(next(r for r in current_report['records'] if r['path']==str(self.b))['status'],'unused')
    def test_missing_usage_is_unknown(self):
        self.cb.GetClipProperty.return_value['Usage']=''
        r=usage.scan(self.project)
        self.assertEqual(next(x for x in r['records'] if x['path']==str(self.b))['status'],'unknown')
    def test_same_source_dedup(self):
        self.cb.GetClipProperty.return_value['File Path']=str(self.a)
        r=usage.scan(self.project)
        self.assertEqual(len(r['records']),1)
        self.assertEqual(r['records'][0]['status'],'used')
    def test_fusion_is_conservative(self):
        self.item.GetFusionCompCount.return_value=1
        r=usage.scan(self.project)
        self.assertEqual(next(x for x in r['records'] if x['path']==str(self.b))['status'],'unknown')
    def test_timeline_only_fusion_transition_does_not_block(self):
        self.item.GetFusionCompCount.return_value=1
        media=MagicMock()
        media.GetAttrs.return_value={'TOOLS_RegID':'MediaIn'}
        media.GetInput.return_value='Timeline'
        merge=MagicMock()
        merge.GetAttrs.return_value={'TOOLS_RegID':'Merge'}
        self.item.GetFusionCompByIndex.return_value.GetToolList.return_value={1:media,2:merge}
        r=usage.scan(self.project)
        self.assertFalse(r['blockers'])
        self.assertEqual(next(x for x in r['records'] if x['path']==str(self.b))['status'],'unused')
        media.GetInput.return_value='MediaPool'
        self.assertTrue(usage.scan(self.project)['blockers'])
        media.GetAttrs.return_value={'TOOLS_RegID':'Loader'}
        self.assertTrue(usage.scan(self.project)['blockers'])

    def test_real_tags_and_undo_preserve_user_additions(self):
        tags.write_tags(str(self.a),['客户标签\n6'])
        r=usage.scan(self.project)
        folder=tags.prepare_report(r,self.root/'reports')
        journal=tags.apply(r,folder)
        self.assertTrue(all(e['state']=='applied' for e in journal['entries']))
        self.assertIn('客户标签\n6',tags.read_tags(str(self.a)))
        self.assertTrue((folder/'未使用候选.savedSearch').exists())
        tags.write_tags(str(self.a),tags.read_tags(str(self.a))+['之后新增\n4'])
        restored,errors=tags.undo(folder/'tag-journal.json')
        self.assertEqual(restored,2);self.assertFalse(errors)
        self.assertEqual(tags.read_tags(str(self.a)),['客户标签\n6','之后新增\n4'])
        self.assertEqual(self.a.read_bytes(),b'test-media-content')
    def test_undo_does_not_override_later_run(self):
        r=usage.scan(self.project)
        folder=tags.prepare_report(r,self.root/'reports')
        tags.apply(r,folder)
        tags.write_tags(str(self.a),[tags.namespace(r)+'newer\n5'])
        restored,errors=tags.undo(folder/'tag-journal.json')
        self.assertEqual(restored,1);self.assertEqual(len(errors),1)
    def test_replaced_file_skipped(self):
        r=usage.scan(self.project)
        replacement=self.root/'new.mov';replacement.write_bytes(b'new')
        replacement.replace(self.a)
        folder=tags.prepare_report(r,self.root/'reports')
        journal=tags.apply(r,folder)
        failed=[e for e in journal['entries'] if e['state']!='applied']
        self.assertEqual(len(failed),1)
    def test_disk_folder_classification_and_undo(self):
        extra=self.root/'nested';extra.mkdir()
        video=extra/'not-imported.MP4';video.write_bytes(b'extra')
        (extra/'sidecar.XML').write_text('metadata')
        (extra/'still.dpx').write_bytes(b'sequence')
        (extra/'alias.mov').symlink_to(self.a)
        r=usage.scan(self.project, disk_folder=str(self.root))
        self.assertEqual(next(x for x in r['records'] if x['path']==str(video))['status'],'not_imported')
        self.assertEqual(len(r['records']),3)
        self.assertEqual(r['diskSkipped'],3)
        folder=tags.prepare_report(r,self.root/'reports')
        journal=tags.apply(r,folder)
        self.assertTrue(all(e['state']=='applied' for e in journal['entries']))
        self.assertTrue((folder/'未导入当前项目.savedSearch').exists())
        self.assertIn('未导入当前项目',tags.read_tags(str(video))[0])
        self.assertEqual(tags.undo(folder/'tag-journal.json'),(3,[]))
        self.assertEqual(tags.read_tags(str(video)),[])
        self.assertEqual(video.read_bytes(),b'extra')
    def test_undo_removes_attribute_when_file_had_no_tags(self):
        r=usage.scan(self.project)
        folder=tags.prepare_report(r,self.root/'reports')
        tags.apply(r,folder)
        self.assertEqual(tags.undo(folder/'tag-journal.json'),(2,[]))
        with self.assertRaises(OSError) as raised:
            tags.get_attribute(str(self.a))
        self.assertIn(raised.exception.errno,(getattr(errno,'ENOATTR',93),errno.ENODATA))
    def test_disk_change_and_import_change_signature(self):
        r=usage.scan(self.project,disk_folder=str(self.root))
        extra=self.root/'new.mov';extra.write_bytes(b'extra')
        changed=usage.scan(self.project,disk_folder=str(self.root))
        self.assertNotEqual(r['signature'],changed['signature'])
        self.pool.GetRootFolder.return_value.GetClipList.return_value.append(self.clip('new',extra,'0'))
        imported=usage.scan(self.project,disk_folder=str(self.root))
        self.assertNotEqual(changed['signature'],imported['signature'])
        self.assertEqual(next(x for x in imported['records'] if x['path']==str(extra))['status'],'unused')
    def test_missing_disk_folder_fails(self):
        with self.assertRaises(ValueError):
            usage.scan(self.project,disk_folder=str(self.root/'absent'))
    def test_disk_hardlink_to_pool_not_classified_unimported(self):
        os.link(self.a,self.root/'alias.mov')
        self.assertEqual(len(usage.scan(self.project,disk_folder=str(self.root))['records']),2)

    def test_excluded_subtree_pruned_from_disk_and_pool(self):
        omit=self.root/'exclude';omit.mkdir();nested=omit/'nested';nested.mkdir()
        hidden=nested/'hidden.mov';hidden.write_bytes(b'media')
        self.pool.GetRootFolder.return_value.GetClipList.return_value.append(self.clip('hidden',hidden,'0'))
        sibling=self.root/'exclude-other';sibling.mkdir();keep=sibling/'keep.mov';keep.write_bytes(b'media')
        report=usage.scan(self.project,disk_folder=str(self.root),excluded_folders=[str(omit)])
        paths={r['path'] for r in report['records']}
        self.assertNotIn(str(hidden),paths);self.assertIn(str(keep),paths)
        self.assertEqual(report['excludedFolders'],[str(omit)])
        self.assertNotEqual(report['signature'],usage.scan(self.project,disk_folder=str(self.root))['signature'])

    def test_multiple_exclusions_and_alias(self):
        omit=self.root/'skip';omit.mkdir();alias=self.root/'alias';alias.symlink_to(omit,target_is_directory=True)
        report=usage.scan(self.project,excluded_folders=[str(alias),str(self.root)])
        self.assertEqual(report['records'],[])
        self.assertIn(str(omit),report['excludedFolders'])

    def test_repeat_scan_signature_stable(self):
        self.assertEqual(usage.scan(self.project)['signature'],usage.scan(self.project)['signature'])

unittest.main()
