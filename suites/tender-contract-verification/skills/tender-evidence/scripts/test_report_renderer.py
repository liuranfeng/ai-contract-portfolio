import copy
import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from report_renderer import render_report, source_id, text_diff

ROOT = Path(__file__).resolve().parent

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.links=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if a.get('href','').startswith('#'):self.links.append(a['href'][1:])

def sample():
    return json.loads((ROOT.parent/'examples/demo.json').read_text(encoding='utf-8'))

class ReportTests(unittest.TestCase):
    def test_explicit_view_and_comparison_without_mutating_snapshot(self):
        d=sample(); c=d['checks'][0]
        c['verification']['status']='partial'
        c['expectationComparison']={'expectation':'<承诺>5年','contract':'3年','impact':'待核对纳入条款','result':'uncertain'}
        d['reportView']={'mainCheckIds':[c['checkId']], 'title':'预期复核', 'summary':'重点复核', 'scope':'仅已登记主题'}
        before=copy.deepcopy(d); md,out=render_report(d)
        self.assertEqual(d,before)
        self.assertEqual(out.count('<section class="case"'),1)
        self.assertIn('预期落实待确认 1',out)
        self.assertIn('&lt;承诺&gt;5年',out)
        self.assertIn('expectation-facts',out)
        self.assertIn('仅已登记主题',out)
        self.assertIn('预期落实待确认',md)

    def test_invalid_explicit_view_or_result_rejected(self):
        from report_renderer import validate_report_options
        d=sample();d['reportView']={'mainCheckIds':['missing']}
        self.assertTrue(validate_report_options(d))
        with self.assertRaises(ValueError):render_report(d)
        d=sample();d['checks'][0]['verification']['status']='implemented'
        d['checks'][0]['expectationComparison']={'expectation':'x','contract':'y','impact':'z','result':'weakened'}
        self.assertTrue(validate_report_options(d))

    def test_explicit_empty_main_keeps_all_checks_as_history(self):
        d=sample();d['reportView']={'mainCheckIds':[]}
        _,out=render_report(d)
        self.assertNotIn('<section class="case"',out)
        self.assertEqual(out.count('<details class="ledger-entry"'),len(d['checks']))
        self.assertIn('主要事项 0',out)

    def test_optional_fields_require_explicit_valid_types(self):
        from report_renderer import validate_report_options
        for view in (False, {'mainCheckIds':[False]}, {'mainCheckIds':[], 'title':False}):
            d=sample();d['reportView']=view
            self.assertTrue(validate_report_options(d))
        for result in (False, 'invented', ''):
            d=sample();d['checks'][0]['expectationComparison']={'expectation':'x','contract':'y','impact':'z','result':result}
            self.assertTrue(validate_report_options(d))

    def test_explicit_labels_do_not_change_original_status(self):
        from report_renderer import EXPECTATION_RESULTS, RESULT_STATUSES
        for result,label in EXPECTATION_RESULTS.items():
            d=sample();c=d['checks'][0]
            status=sorted(RESULT_STATUSES[result])[0];c['verification']['status']=status
            c['expectationComparison']={'expectation':'x','contract':'y','impact':'z','result':result}
            d['reportView']={'mainCheckIds':[c['checkId']],'title':'<script>bad</script>'}
            _,out=render_report(d)
            self.assertIn(label+' 1',out)
            self.assertEqual(c['verification']['status'],status)
            self.assertNotIn('<script>bad</script>',out)

    def test_legacy_partial_not_inferred_as_expectation_loss(self):
        d=sample()
        for c in d['checks']:c['verification']['status']='partial'
        _,out=render_report(d)
        self.assertNotIn('已证实低于预期',out)
        self.assertIn('部分对应 / 待明确',out)
        self.assertIn('print-full',out)
        self.assertIn("d.classList.contains('contents')",out)
        self.assertIn('window.tenderPreparePrint=function',out)
        self.assertIn('window.tenderRestorePrint=function',out)
        self.assertIn("card.querySelector('.quote')?.textContent.includes(text)",out)
        self.assertIn("a.getAttribute('href')===anchor.getAttribute('href')",out)
        self.assertIn('原文已在本事项证据卡展示',out)
        self.assertIn('.contents{display:block;break-inside:auto}',out)
        self.assertNotIn('打印时自动展开全部附录',out)
    def test_all_links_resolve_and_ids_unique(self):
        d=sample(); _,out=render_report(d)
        parsed=Links();parsed.feed(out)
        self.assertEqual(len(parsed.ids),len(set(parsed.ids)))
        self.assertEqual(set(parsed.links)-set(parsed.ids),set())
        for c in d['checks']:self.assertIn(c['title'],out)
        self.assertIn('document-flow',out)

    def test_composite_id_preserves_type_and_document(self):
        self.assertEqual(len({source_id({'documentIndex':d,'layoutId':i}) for d in (0,1) for i in (12,'12')}),4)

    def test_diff_keeps_original_text_and_escapes_markup(self):
        import html,re
        a,b='<script>x</script>2年','<img>3年'
        left,right=text_diff(a,b)
        self.assertNotIn('<script>',left)
        self.assertEqual(html.unescape(re.sub('</?mark>','',left)),a)
        self.assertEqual(html.unescape(re.sub('</?mark>','',right)),b)

    def test_no_invented_relation(self):
        d=sample()
        for c in d['checks']:c['relations']=[]
        _,out=render_report(d)
        self.assertNotIn('<div class="connector ',out)
        self.assertIn('未登记成对关系',out)

    def test_process_mode_does_not_bypass_final_gate(self):
        d=sample();d['coverage'][0]['status']='needs_review'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'input.json';src.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
            original=src.read_bytes()
            cmd=[sys.executable,str(ROOT/'evidence.py'),'report',str(src)]
            final=subprocess.run(cmd+[str(root/'final')],capture_output=True)
            self.assertNotEqual(final.returncode,0);self.assertFalse((root/'final').exists())
            process=subprocess.run(cmd+[str(root/'process'),'--process'],capture_output=True)
            self.assertEqual(process.returncode,0,process.stderr)
            manifest=json.loads((root/'process/report-manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['reportMode'],'process')
            self.assertIn('Unresolved coverage',manifest['finalGateErrors'])
            self.assertEqual(src.read_bytes(),original)
            self.assertIn('非正式交付',(root/'process/report.html').read_text(encoding='utf-8'))
            again=subprocess.run(cmd+[str(root/'process'),'--process'],capture_output=True)
            self.assertNotEqual(again.returncode,0)

if __name__=='__main__':unittest.main()
