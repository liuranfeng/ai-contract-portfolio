"""Native IDs, reading order and credential-safe provenance; offline only."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import test_baidu_async_parser as support

Transport, parser, responses = support.Transport, support.parser, support.responses


class NativeLayoutTest(unittest.TestCase):
    def test_missing_or_invalid_native_id_is_rejected(self):
        for value in (None, '', '  ', True, [], {}):
            with self.subTest(value=value):
                with self.assertRaises(parser.ParseError) as error:
                    parser._normalize({'pages': [{'layouts': [{'layout_id': value, 'text': '正文'}]}]})
                self.assertEqual('native_layout_id_required', error.exception.code)

    def test_duplicate_ids_are_rejected_even_across_pages(self):
        with self.assertRaises(parser.ParseError) as error:
            parser._normalize({'pages': [{'layouts': [{'layout_id': 'a', 'text': '甲'}]},
                                         {'layouts': [{'layout_id': 'a', 'text': ''}]}]})
        self.assertEqual('duplicate_layout_id', error.exception.code)

    def test_order_and_id_types_are_preserved(self):
        raw = {'pages': [{'page_num': 8, 'layouts': [{'layout_id': 0, 'text': '甲'},
                    {'layout_id': '0', 'text': '乙'}]}, {'page_num': 2, 'layouts': [
                    {'layout_id': 'last', 'text': '丙', 'position': [8, 9, 2, 3]}]}]}
        snapshot = copy.deepcopy(raw)
        _, pages, _, _ = parser._normalize(raw)
        self.assertEqual([8, 2], [p['page_num'] for p in pages])
        self.assertEqual([0, '0', 'last'], [l['layout_id'] for p in pages for l in p['layouts']])
        self.assertEqual(snapshot, raw)

    def test_table_enrichment_preserves_service_text(self):
        raw = {'pages': [{'layouts': [{'layout_id': 'table-1', 'type': 'table', 'text': ''}],
                          'tables': [{'layout_id': 'table-1', 'table_html': '<table><tr><td>金额</td><td>100元</td></tr></table>'}]}]}
        _, pages, _, _ = parser._normalize(raw)
        layout = pages[0]['layouts'][0]
        self.assertEqual('', layout['text_raw'])
        self.assertIn('100元', layout['text'])


class ArchiveTest(unittest.TestCase):
    setUp = support.BaiduAsyncParserTest.setUp
    run_parse = support.BaiduAsyncParserTest.run_parse

    def test_raw_structure_has_hash_and_original_service_layouts(self):
        original = responses()[-1]
        result = self.run_parse(Transport(responses()))
        metadata = json.loads(Path(result['metadata']).read_text(encoding='utf-8'))
        self.assertIn('raw_parse_file', metadata)
        archive = Path(result['metadata']).parent / metadata['raw_parse_file']
        self.assertEqual(original, json.loads(archive.read_text(encoding='utf-8')))
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), metadata['raw_parse_sha256'])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), metadata['source_sha256'])
        self.assertTrue(metadata['parse_run_id'])

    def test_archive_redacts_secrets_and_signed_urls(self):
        items = responses()
        items[-1]['transport'] = {'api_key': 'archive-api-secret', 'Authorization': 'Bearer secret-value',
            'image_url': 'https://example.bj.bcebos.com/p.png?authorization=signed-secret',
            'nested': ['https://example.com/result?X-Amz-Signature=private-signature']}
        items[-1]['debug'] = 'test-not-a-real-key'
        result = self.run_parse(Transport(items))
        combined = ''.join(p.read_text(encoding='utf-8') for p in self.out.iterdir())
        for secret in ('archive-api-secret', 'secret-value', 'signed-secret', 'private-signature', 'test-not-a-real-key'):
            self.assertNotIn(secret, combined)
        metadata = json.loads(Path(result['metadata']).read_text(encoding='utf-8'))
        self.assertTrue(metadata.get('archive_redacted_paths'))

    def test_missing_id_archives_raw_but_has_no_success_metadata(self):
        items = responses()
        items[-1]['pages'][0]['layouts'][0].pop('layout_id')
        with self.assertRaises(parser.ParseError):
            self.run_parse(Transport(items))
        self.assertEqual(1, len(list(self.out.glob('*_raw_parse.json'))))
        self.assertFalse(list(self.out.glob('*_parsed.*')))


if __name__ == '__main__':
    unittest.main()
