import copy
import unittest
import json
from pathlib import Path
from evidence import import_layouts, validate, resolve, render


def fixture():
    docs = []
    for i, role in enumerate(['tender', 'bid', 'contract']):
        docs.append({'documentIndex': i, 'name': role, 'role': role,
                     'parseRunId': 'run-1', 'sourceSha256': 'a' * 64,
                     'rawParseSha256': 'b' * 64, 'status': 'complete',
                     'layouts': [{'layoutId': 12, 'text': ['至少三年', '市区五年', '三年'][i], 'page': 1}]})
    ref = {'documentIndex': 1, 'layoutId': 12}
    return {'schemaVersion': '1.0.0', 'projectId': 'demo', 'snapshotId': 's1',
            'documents': docs, 'missingMaterials': [],
            'facts': [{'factId': 'F1', 'fields': {'scope': '市区'},
                       'fieldSources': {'scope': [ref]},
                       'primarySources': [ref], 'contextSources': [],
                       'quotes': [{'source': ref, 'text': '市区五年'}]}],
            'checks': [{'checkId': 'C1', 'title': '质保', 'factIds': ['F1'],
                        'relations': [], 'verification': {'status': 'pending', 'reason': '待核验',
                        'comparedFields': [], 'reviewedSources': [], 'missingMaterials': [],
                        'suggestion': '', 'reviewNote': ''}}],
            'coverage': []}


class EvidenceTests(unittest.TestCase):
    def test_same_id_different_documents(self):
        data = fixture()
        self.assertEqual(resolve(data, {'documentIndex': 0, 'layoutId': 12})['text'], '至少三年')
        self.assertEqual(resolve(data, {'documentIndex': 1, 'layoutId': 12})['text'], '市区五年')
        self.assertEqual(validate(data), [])

    def test_import_preserves_numeric_zero_and_alias(self):
        self.assertEqual(import_layouts({'pages': [{'page_num': 0, 'layouts': [{'layout_id': 0, 'text': 'A'}]}]})[0]['layoutId'], 0)

    def test_missing_and_duplicate_ids_rejected(self):
        for blocks in [[{'text': 'A'}], [{'layoutId': 1, 'text': 'A'}, {'layoutId': 1, 'text': 'B'}]]:
            with self.assertRaises(ValueError):
                import_layouts({'pages': [{'layouts': blocks}]})

    def test_id_type_not_coerced(self):
        with self.assertRaises(ValueError):
            resolve(fixture(), {'documentIndex': 1, 'layoutId': '12'})

    def test_fabricated_source_rejected(self):
        d = fixture(); d['facts'][0]['primarySources'][0]['layoutId'] = 'table_row_8'
        self.assertTrue(validate(d))

    def test_quote_mismatch_rejected(self):
        d = fixture(); d['facts'][0]['quotes'][0]['text'] = '全部地区五年'
        self.assertTrue(validate(d))

    def test_fields_need_evidence(self):
        d = fixture(); d['facts'][0]['fields']['trigger'] = '通知后'
        self.assertTrue(validate(d))

    def test_missing_attachment_blocks_not_found(self):
        d = fixture(); d['missingMaterials'] = ['附件二']
        d['checks'][0]['verification']['status'] = 'not_found'
        self.assertTrue(validate(d, final=True))

    def test_final_blocks_pending(self):
        self.assertTrue(validate(fixture(), final=True))

    def test_report_escapes_untrusted_text(self):
        d = fixture(); d['documents'][0]['layouts'][0]['text'] = '<script>alert(1)</script>'
        md, html = render(d)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('证据', md)

    def test_complete_sample_and_snapshot_isolation(self):
        d = json.loads((Path(__file__).parents[1] / 'examples/demo.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(d, final=True), [])
        old = copy.deepcopy(d)
        d['snapshotId'] = 'demo-2'
        d['documents'][1]['parseRunId'] = 'new-run'
        d['documents'][1]['layouts'][0]['layoutId'] = 99
        self.assertTrue(validate(d))
        self.assertEqual(validate(old, final=True), [])

    def test_not_found_requires_all_contract_blocks(self):
        d = json.loads((Path(__file__).parents[1] / 'examples/demo.json').read_text(encoding='utf-8'))
        v = d['checks'][0]['verification']; v['status'] = 'not_found'
        v['reviewedSources'] = [{'documentIndex': 0, 'layoutId': 12}]
        self.assertTrue(validate(d, final=True))

    def test_full_coverage_cannot_be_omitted(self):
        d = json.loads((Path(__file__).parents[1] / 'examples/demo.json').read_text(encoding='utf-8'))
        d['coverage'].pop()
        self.assertTrue(validate(d, final=True))

    def test_conflicting_aliases_rejected(self):
        with self.assertRaises(ValueError):
            import_layouts({'pages': [{'layouts': [{'layoutId': 1, 'layout_id': 2, 'text': 'A'}]}]})

    def test_baidu_table_content_and_coordinates(self):
        raw = {'pages': [{'page_num': 0, 'layouts': [{'layout_id': 't1', 'text': '', 'type': 'table', 'position': [1,2,3,4]}],
                          'tables': [{'layout_id': 't1', 'markdown': '|培训|四次|'}]}]}
        block = import_layouts(raw)[0]
        self.assertEqual(block['layoutId'], 't1')
        self.assertEqual(block['text'], '|培训|四次|')
        self.assertEqual(block['layoutText'], '')
        self.assertEqual(block['bbox'], [1,2,3,4])
        self.assertEqual(block['textSource'], 'tables.markdown')


if __name__ == '__main__':
    unittest.main()
