"""Check source and archive integrity with simulated service responses."""
import importlib.util
import json
from pathlib import Path
import unittest

import test_baidu_async_parser as support

SPEC = importlib.util.spec_from_file_location('compare_parse_gate', support.ROOT / 'scripts/parse_gate_check.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class GateTest(unittest.TestCase):
    setUp = support.BaiduAsyncParserTest.setUp
    run_parse = support.BaiduAsyncParserTest.run_parse

    def result(self):
        items = support.responses()
        items[-1]['pages'][0]['layouts'][0]['layout_id'] = 0
        result = self.run_parse(support.Transport(items))
        path = Path(result['metadata'])
        return path, json.loads(path.read_text(encoding='utf-8'))

    def test_zero_id_passes_source_and_archive_gate(self):
        path, _ = self.result()
        self.assertEqual(0, gate.verify(path, self.source, True)[0])

    def test_tampered_archive_fails_gate(self):
        path, meta = self.result()
        (path.parent / meta['raw_parse_file']).write_text('{}', encoding='utf-8')
        self.assertEqual(1, gate.verify(path, self.source, False)[0])

    def test_blank_layout_duplicate_id_is_rejected(self):
        path, meta = self.result()
        meta['pages'][0]['layouts'][0]['layout_id'] = 'first'
        meta['pages'][0]['layouts'].append({'layout_id': 'first', 'text': ''})
        path.write_text(json.dumps(meta), encoding='utf-8')
        self.assertEqual(1, gate.verify(path, self.source, True)[0])

    def test_missing_source_is_not_claimed_verified(self):
        path, _ = self.result()
        self.assertEqual(1, gate.verify(path, None, True)[0])


if __name__ == '__main__':
    unittest.main()
