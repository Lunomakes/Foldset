"""W1 presentation: counts and the decision trace come straight from the scan report, unchanged."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Integrations/DaVinciResolve'))
import foldset_usage_ui as view

# Shaped like the reloaded Resolve 21.1.1 QA Fusion scan (all-strict: used 1, unused 0, unknown 2), paths anonymised.
FUSION = {'project': 'Foldset QA Fusion', 'scope': 'all', 'timelines': ['QA Fusion'],
          'records': [{'path': '/Volumes/QA/camera-a.mov', 'status': 'used'},
                      {'path': '/Volumes/QA/camera-b.mov', 'status': 'unknown'},
                      {'path': '/Volumes/QA/unused-control.mov', 'status': 'unknown'}],
          'blockers': ['Fusion 节点依赖待核实：Loader（camera-a.mov）'],
          'skipped': [{'name': 'QA Fusion', 'reason': '无独立源文件（时间线、复合片段或生成器）'}],
          'diskFolder': '/Volumes/QA', 'diskSkipped': 0, 'excludedFolders': [],
          'ignoreCompounds': False, 'ignoredDependencies': []}


def counts(report):
    return {kind: count for kind, _, count, _ in view.count_rows(report)}


class ReportViewTests(unittest.TestCase):
    def test_counts_match_scan_records(self):
        c = counts(FUSION)
        self.assertEqual((c['used'], c['unused'], c['unknown']), (1, 0, 2))
        self.assertEqual((c['not_imported'], c['skipped']), (0, 1))

    def test_before_scan_shows_no_numbers(self):
        self.assertTrue(all(count is None for _, _, count, _ in view.count_rows(None)))
        self.assertNotIn('not_imported', counts(None))

    def test_not_imported_row_only_with_disk_folder(self):
        self.assertNotIn('not_imported', counts(dict(FUSION, diskFolder=None)))

    def test_blockers_are_explained_as_project_wide(self):
        text = view.report_html(FUSION)
        self.assertIn('为什么有 2 个文件归入“待核实”', text)
        self.assertIn('这是对整个项目的判断', text)
        self.assertIn('Loader（camera-a.mov）', text)

    def test_unknown_without_blockers_names_missing_usage(self):
        text = view.report_html(dict(FUSION, blockers=[]))
        self.assertIn('缺少可确认的使用信息', text)
        self.assertNotIn('为什么有', text)

    def test_current_scope_warns_about_other_timelines(self):
        self.assertIn('其他时间线可能仍使用', view.report_html(dict(FUSION, scope='current')))

    def test_names_are_escaped(self):
        text = view.report_html(dict(FUSION, project='<b>x</b>', blockers=['a<script>']))
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', text)

    def test_problems_listed_after_report(self):
        text = view.report_html(FUSION, ['/Volumes/QA/a.mov：权限不足'], '写入失败')
        self.assertIn('写入失败', text)
        self.assertGreater(text.index('写入失败'), text.index('这次怎样判定'))

    def test_long_paths_can_wrap(self):
        text = view.report_html(dict(FUSION, diskFolder='/Volumes/QA/very/long/media', excludedFolders=['/Volumes/QA/x']))
        self.assertIn('/\u200bVolumes/\u200bQA/\u200bvery', text)
        self.assertIn('/\u200bVolumes/\u200bQA/\u200bx', text)

    def test_pasted_folder_quotes_are_removed(self):
        self.assertEqual(view.clean_folder("'/Volumes/QA/media'"), '/Volumes/QA/media')
        self.assertEqual(view.clean_folder(' "/Volumes/QA/my media" \n'), '/Volumes/QA/my media')
        self.assertEqual(view.clean_folder("/Volumes/QA/it's"), "/Volumes/QA/it's")
        self.assertTrue(view.clean_folder('~/Movies').endswith('/Movies'))
        self.assertIsNone(view.clean_folder("  ''  "))
        self.assertIsNone(view.clean_folder(''))

    def test_status_line_is_escaped_and_toned(self):
        line = view.status_html('扫描失败：<x>', 'bad')
        self.assertIn('#ff6961', line)
        self.assertIn('&lt;x&gt;', line)

unittest.main()
