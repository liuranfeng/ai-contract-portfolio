"""Offline regression tests for physical lineage and non-truncating analysis windows."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from document_chunks import split_pdf, verify_manifest, chunk_plan, map_layouts
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, RectangleObject


def pdf(path, count=7):
    writer = PdfWriter()
    for i in range(count):
        page = writer.add_blank_page(width=600, height=800)
        page.cropbox = RectangleObject([10, 20, 590, 780])
        page.rotate(90 if i % 2 else 0)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(('BT /F1 12 Tf 40 40 Td (PAGE %s) Tj ET\n' % (i + 1)).encode() + b'% padding\n' * 300)
        page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as f:
        writer.write(f)


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.pdf'
        pdf(self.source)

    def split(self, **kw):
        return split_pdf(self.source, self.root / 'chunks', parent_document_index=0,
                         child_index_start=10, max_pages=3, max_bytes=10_000_000, **kw)

    def test_page_mapping_and_appearance(self):
        manifest = self.split()
        self.assertEqual([len(c['pages']) for c in manifest['chunks']], [3, 3, 1])
        original = PdfReader(self.source)
        for c in manifest['chunks']:
            reader = PdfReader(self.root / 'chunks' / c['file'])
            for mapping in c['pages']:
                before = original.pages[mapping['originalPage'] - 1]
                after = reader.pages[mapping['chunkPage'] - 1]
                self.assertEqual(before.extract_text(), after.extract_text())
                self.assertEqual(list(before.cropbox), list(after.cropbox))
                self.assertEqual(before.rotation, after.rotation)
        self.assertTrue(verify_manifest(self.root / 'chunks' / 'manifest.json')['valid'])
        with self.assertRaises(FileExistsError):
            self.split()

    def test_size_limit_and_single_page_failure(self):
        manifest = split_pdf(self.source, self.root / 'small', 0, 10, 7, 8000)
        self.assertGreater(len(manifest['chunks']), 1)
        self.assertTrue(all(c['bytes'] <= 8000 for c in manifest['chunks']))
        with self.assertRaisesRegex(ValueError, 'single page'):
            split_pdf(self.source, self.root / 'impossible', 0, 10, 7, 50)
        self.assertFalse((self.root / 'impossible' / 'manifest.json').exists())

    def test_detect_gap_overlap_missing_tamper(self):
        manifest = self.split()
        path = self.root / 'chunks' / 'manifest.json'
        for mutate in [lambda m: m['chunks'].pop(),
                       lambda m: m['chunks'][1]['pages'][0].update(originalPage=1),
                       lambda m: m['chunks'][1].update(documentIndex=10),
                       lambda m: m['chunks'][0].update(file='missing.pdf')]:
            bad = copy.deepcopy(manifest)
            mutate(bad)
            path.write_text(json.dumps(bad), encoding='utf-8')
            self.assertFalse(verify_manifest(path)['valid'])
        path.write_text(json.dumps(manifest), encoding='utf-8')
        (self.root / 'chunks' / manifest['chunks'][0]['file']).write_bytes(b'bad')
        self.assertFalse(verify_manifest(path)['valid'])

    def test_child_index_cannot_alias_parent(self):
        with self.assertRaises(ValueError):
            split_pdf(self.source, self.root / 'alias', 10, 10, 3, 10000)

    def test_source_change_is_detected(self):
        self.split()
        pdf(self.source, count=6)
        result = verify_manifest(self.root / 'chunks' / 'manifest.json')
        self.assertFalse(result['valid'])
        self.assertIn('Source hash mismatch', result['errors'])

    def test_final_verification_failure_never_leaves_complete_manifest(self):
        with patch('document_chunks.verify_manifest', return_value={'valid': False, 'errors': ['simulated failure']}):
            with self.assertRaisesRegex(ValueError, 'failed verification'):
                self.split()
        path = self.root / 'chunks' / 'manifest.json'
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['status'], 'failed')
        self.assertFalse(verify_manifest(path)['valid'])

    def test_cli_plan_exclusive_output(self):
        snapshot = self.root / 'snapshot.json'
        output = self.root / 'windows.json'
        snapshot.write_text(json.dumps({'documents': [{'documentIndex': 0, 'layouts': [
            {'layoutId': 'a', 'text': 'a' * 8}, {'layoutId': 'b', 'text': 'b' * 8}]}]}), encoding='utf-8')
        command = [sys.executable, '-X', 'utf8', str(Path(__file__).with_name('document_chunks.py')),
                   'chunk-plan', str(snapshot), str(output), '--max-chars', '10']
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        saved = output.read_bytes()
        self.assertTrue(json.loads(saved)['windows'][0]['needsContextFollowup'])
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(saved, output.read_bytes())

    def test_mapping_explicit_base_and_native_identity(self):
        self.split()
        path = self.root / 'chunks' / 'manifest.json'
        imported = {'rawParseSha256': 'a' * 64, 'layouts': [
            {'layoutId': 1, 'page': 0, 'text': 'a'},
            {'layoutId': '1', 'page': 2, 'text': 'b'}]}
        result = map_layouts(path, 11, imported, page_base=0)
        self.assertEqual([b['originalPage'] for b in result['layouts']], [4, 6])
        self.assertEqual([b['page'] for b in result['layouts']], [0, 2])
        self.assertEqual(result['parentDocumentIndex'], 0)
        self.assertEqual(result['documentIndex'], 11)
        self.assertIsInstance(result['layouts'][0]['layoutId'], int)
        self.assertIsInstance(result['layouts'][1]['layoutId'], str)
        self.assertNotIn('originalPage', imported['layouts'][0])
        imported['layouts'][0]['page'] = 1
        imported['layouts'][1]['page'] = 3
        result = map_layouts(path, 11, imported, page_base=1)
        self.assertEqual([b['originalPage'] for b in result['layouts']], [4, 6])

    def test_mapping_rejects_bad_pages_conflicts_and_tampered_manifest(self):
        self.split()
        path = self.root / 'chunks' / 'manifest.json'
        base = {'rawParseSha256': 'a' * 64, 'layouts': [{'layoutId': 'a', 'page': 1, 'text': 'a'}]}
        for page in [True, '1', 1.5, -1, 0, 4, None]:
            value = copy.deepcopy(base)
            value['layouts'][0]['page'] = page
            with self.assertRaises(ValueError):
                map_layouts(path, 11, value, page_base=1)
        value = copy.deepcopy(base)
        value['layouts'][0]['originalPage'] = 1
        with self.assertRaisesRegex(ValueError, 'originalPage'):
            map_layouts(path, 11, value, page_base=1)
        with self.assertRaises(ValueError):
            map_layouts(path, 99, base, page_base=1)
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['chunks'].pop()
        path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            map_layouts(path, 11, base, page_base=1)


class PlanTests(unittest.TestCase):
    def test_ownership_types_context_and_oversize(self):
        source = {'documents': [
            {'documentIndex': 0, 'layouts': [{'layoutId': 1, 'text': 'abc'}, {'layoutId': '1', 'text': 'def'}, {'layoutId': 'big', 'text': 'x' * 50}]},
            {'documentIndex': 1, 'layouts': [{'layoutId': 1, 'text': 'same id new doc'}]}]}
        result = chunk_plan(source, max_chars=10, context_blocks=1)
        owners = [r for w in result['windows'] for r in w['primaryRefs']]
        self.assertEqual(len(owners), 4)
        self.assertIsInstance(owners[0]['layoutId'], int)
        self.assertIsInstance(owners[1]['layoutId'], str)
        self.assertTrue(any(w['oversizeBlock'] for w in result['windows']))
        for w in result['windows']:
            self.assertTrue(w['totalChars'] <= 10 or w['oversizeBlock'])
            self.assertTrue(all(r['documentIndex'] == w['documentIndex'] for r in w['contextRefs']))
        self.assertEqual(source['documents'][0]['layouts'][2]['text'], 'x' * 50)

    def test_duplicate_refs_rejected(self):
        source = {'documents': [{'documentIndex': 0, 'layouts': [{'layoutId': 'a', 'text': ''}, {'layoutId': 'a', 'text': ''}]}]}
        with self.assertRaises(ValueError):
            chunk_plan(source)


if __name__ == '__main__':
    unittest.main()
