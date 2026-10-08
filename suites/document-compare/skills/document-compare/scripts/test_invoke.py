import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from docx import Document
from invoke import invoke


class InvocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        for stem, term in [('approved', '90'), ('signing', '120')]:
            lines = ['模拟合同（插件测试）', f'付款期为{term}日。']
            d = Document()
            for text in lines:
                d.add_paragraph(text)
            file = self.home / (stem + '.docx')
            d.save(file)
            parsed = {'fixture':True, 'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(), 'pages':[{'layouts':[{'layout_id':'native-'+str(i), 'text':text} for i,text in enumerate(lines)]}]}
            (self.home / (stem + '.json')).write_text(json.dumps(parsed), encoding='utf8')
        self.request = {'schemaVersion':'1.0', 'mode':'character', 'useCase':'pre_sign',
                        'original':{'parsedPath':'approved.json','sourcePath':'approved.docx'},
                        'candidate':{'parsedPath':'signing.json','sourcePath':'signing.docx'},
                        'context':{'contractId':'DEMO', 'approvalId':'APP-DEMO', 'approvedVersionId':'V03', 'approvedSourceSha256':hashlib.sha256((self.home/'approved.docx').read_bytes()).hexdigest()}}

    def test_pre_sign_produces_real_redline_binds_approved_and_does_not_decide(self):
        before = (self.home/'approved.docx').read_bytes()
        result = invoke(self.request, self.home/'out', self.home)
        self.assertEqual(result['exportStatus'], 'complete', result)
        self.assertEqual(result['binding']['approvedVersionId'], 'V03')
        self.assertEqual(result['changedItems'], 1)
        self.assertEqual(result['businessDecision'], 'not_made_by_plugin')
        with zipfile.ZipFile(self.home/'out/tracked.docx') as z:
            xml = z.read('word/document.xml')
            self.assertIn(b'<w:ins ', xml)
            self.assertIn(b'<w:del ', xml)
        self.assertEqual(before, (self.home/'approved.docx').read_bytes())
        manifest = json.loads((self.home/'out/tracked.docx.manifest.json').read_text(encoding='utf8'))
        self.assertTrue(manifest)

    def test_standalone_works_without_contract_or_approval(self):
        r = copy.deepcopy(self.request);r['useCase']='standalone';r.pop('context');r['outputs']=['html']
        result=invoke(r,self.home/'out',self.home)
        self.assertIsNone(result['binding'])
        self.assertTrue((self.home/'out/comparison.html').is_file())

    def test_wrong_approval_hash_is_refused_before_export(self):
        self.request['context']['approvedSourceSha256']='0'*64
        with self.assertRaisesRegex(ValueError,'审批通过版摘要不匹配'):
            invoke(self.request,self.home/'out',self.home)
        self.assertFalse((self.home/'out').exists())

    def test_unbound_parser_data_is_refused(self):
        file=self.home/'signing.json';raw=json.loads(file.read_text());raw.pop('source_sha256');file.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'source_sha256'):
            invoke(self.request,self.home/'out',self.home)

    def test_missing_approval_context_is_refused(self):
        self.request['context'].pop('approvalId')
        with self.assertRaisesRegex(ValueError,'审批'):
            invoke(self.request,self.home/'out',self.home)

    def test_semantic_without_judgment_stays_pending(self):
        self.request['mode']='semantic'
        result=invoke(self.request,self.home/'out',self.home)
        self.assertEqual(result['comparisonStatus'],'needs_review')
        self.assertEqual(result['businessDecision'],'not_made_by_plugin')

    def test_signing_cannot_omit_tracked_output(self):
        self.request['outputs']=['html']
        with self.assertRaisesRegex(ValueError,'Word 修订'):
            invoke(self.request,self.home/'out',self.home)

    def test_explicit_reading_order_alignment_supported(self):
        p=self.home/'alignment.json';p.write_text(json.dumps([{'left':[0],'right':[0]},{'left':[1],'right':[1]}]))
        self.request['alignmentPath']='alignment.json'
        self.assertEqual(invoke(self.request,self.home/'out',self.home)['changedItems'],1)


if __name__=='__main__':unittest.main()
