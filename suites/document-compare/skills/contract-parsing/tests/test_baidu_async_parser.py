"""Contract tests against documented task/query payloads; no live credentials."""
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('async_parser', ROOT / 'scripts/document_parse_skill.py')
parser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parser)


class Transport:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def open(self, request, timeout=120):
        self.requests.append(request)
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(value if isinstance(value, bytes) else json.dumps(value).encode())


def responses(status='success'):
    return [
        {'error_code': 0, 'result': {'task_id': 'task-test'}},
        {'error_code': 0, 'result': {'task_id': 'task-test', 'status': status,
            'markdown_url': 'https://example.bj.bcebos.com/result.md',
            'parse_result_url': 'https://example.bj.bcebos.com/result.json'}},
        '# 合同\n\n| 价款 | 金额 |\n| --- | --- |\n| 货款 | 100元 |'.encode(),
        {'file_name': '合同.pdf', 'pages': [{'page_num': 0, 'text': '合同 货款 100元',
            'layouts': [{'layout_id': 'p0-title', 'type': 'doc_title', 'text': '合同', 'position': [0, 0, 80, 20]},
                        {'layout_id': 'p0-table', 'type': 'table', 'text': '', 'position': [0, 20, 80, 100]}],
            'tables': [{'layout_id': 'p0-table', 'markdown': '| 价款 | 金额 |\n| --- | --- |\n| 货款 | 100元 |'}]}]},
    ]


class BaiduAsyncParserTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / '合同.pdf'
        self.source.write_bytes(b'%PDF-test-input')
        self.out = self.root / 'outputs'
        self.env = patch.dict(os.environ, {'QIANFAN_API_KEY': 'test-not-a-real-key'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_parse(self, transport, **kwargs):
        with patch.object(parser, 'build_opener', return_value=transport), patch('time.sleep'):
            return parser.parse_file(self.source, self.out, **kwargs)

    def test_bearer_task_query_and_unauthenticated_result_downloads(self):
        transport = Transport(responses())
        result = self.run_parse(transport)
        self.assertTrue(result['ok'])
        requests = transport.requests
        self.assertEqual('https://aip.baidubce.com/rest/2.0/brain/online/v2/paddle-vl-parser/task', requests[0].full_url)
        self.assertEqual(requests[0].full_url + '/query', requests[1].full_url)
        self.assertEqual('Bearer test-not-a-real-key', requests[0].get_header('Authorization'))
        form = parse_qs(requests[0].data.decode())
        self.assertEqual(self.source.read_bytes(), base64.b64decode(form['file_data'][0]))
        self.assertEqual(['合同.pdf'], form['file_name'])
        self.assertEqual({'task_id': ['task-test']}, parse_qs(requests[1].data.decode()))
        self.assertTrue(all(r.get_header('Authorization') is None for r in requests[2:]))
        self.assertTrue(all('access_token' not in r.full_url for r in requests))
        meta = json.loads(Path(result['metadata']).read_text(encoding='utf-8'))
        self.assertEqual('baidu-document-parser/paddle-vl', meta['parser'])
        self.assertEqual('qianfan_api_key', meta['auth_source'])
        self.assertIn('100元', meta['pages'][0]['layouts'][1]['text'])
        self.assertEqual('p0-table', meta['pages'][0]['layouts'][1]['layout_id'])
        self.assertTrue(meta['layout_available'])
        self.assertNotIn('test-not-a-real-key', ''.join(p.read_text(encoding='utf-8') for p in self.out.iterdir()))

    def test_missing_key_does_not_use_dumate_or_local_parser(self):
        with patch.dict(os.environ, {'DUMATE_SESSION_ID': 'old-session'}, clear=True):
            with self.assertRaises(parser.ParseError) as failure:
                self.run_parse(Transport([]))
        self.assertEqual('api_key_required', failure.exception.code)
        self.assertFalse(self.out.exists())

    def test_status_is_not_remote_verification(self):
        result = parser.safe_route(parser.resolve_route())
        self.assertFalse(result['remote_verified'])
        self.assertNotIn('test-not-a-real-key', json.dumps(result))

    def test_business_error_blocks_without_success_outputs(self):
        with self.assertRaises(parser.ParseError):
            self.run_parse(Transport([{'error_code': 110, 'error_msg': 'test-not-a-real-key invalid'}]))
        self.assertFalse(list(self.out.glob('*_parsed.*')))

    def test_http_auth_rejection_sanitizes_error(self):
        error = HTTPError('https://aip.baidubce.com/', 403, 'test-not-a-real-key', {}, None)
        with self.assertRaises(parser.ParseError) as failure:
            self.run_parse(Transport([error]))
        self.assertEqual('api_key_rejected', failure.exception.code)
        self.assertNotIn('test-not-a-real-key', str(failure.exception))

    def test_pending_then_success_polls_without_resubmission(self):
        items = responses()
        items.insert(1, {'error_code': 0, 'result': {'task_id': 'task-test', 'status': 'pending'}})
        t = Transport(items)
        self.assertTrue(self.run_parse(t)['ok'])
        self.assertEqual(1, sum(r.full_url.endswith('/task') for r in t.requests))

    def test_timeout_retains_resumable_job_not_success(self):
        with self.assertRaises(parser.ParseError) as failure:
            self.run_parse(Transport(responses('processing')[:2]), max_polls=1)
        self.assertEqual('parse_pending', failure.exception.code)
        self.assertEqual(1, len(list(self.out.glob('*_job.json'))))
        self.assertFalse(list(self.out.glob('*_parsed.*')))
        job = next(self.out.glob('*_job.json'))
        t = Transport(responses()[1:])
        self.assertTrue(self.run_parse(t, resume_job=job)['ok'])
        self.assertTrue(t.requests[0].full_url.endswith('/query'))

    def test_resume_rejects_different_source_before_network(self):
        with self.assertRaises(parser.ParseError):
            self.run_parse(Transport(responses('pending')[:2]), max_polls=1)
        self.source.write_bytes(b'changed')
        with self.assertRaises(parser.ParseError) as failure:
            self.run_parse(Transport([]), resume_job=next(self.out.glob('*_job.json')))
        self.assertEqual('resume_source_mismatch', failure.exception.code)

    def test_failed_task_no_fallback(self):
        with self.assertRaises(parser.ParseError) as failure:
            self.run_parse(Transport(responses('failed')[:2]))
        self.assertEqual('document_parse_failed', failure.exception.code)
        self.assertFalse(list(self.out.glob('*_parsed.*')))

    def test_result_host_is_restricted_before_download(self):
        items = responses()
        items[1]['result']['markdown_url'] = 'http://127.0.0.1/secrets'
        with self.assertRaises(parser.ParseError) as failure:
            self.run_parse(Transport(items))
        self.assertEqual('invalid_result_url', failure.exception.code)

    def test_missing_result_file_blocks(self):
        items = responses()
        items[1]['result'].pop('parse_result_url')
        with self.assertRaises(parser.ParseError):
            self.run_parse(Transport(items))
        self.assertFalse(list(self.out.glob('*_parsed.*')))

    def test_same_name_does_not_overwrite(self):
        first = self.run_parse(Transport(responses()))
        second = self.run_parse(Transport(responses()))
        self.assertNotEqual(first['metadata'], second['metadata'])
        self.assertTrue(Path(first['metadata']).exists())

    def test_non_supported_file_does_not_fall_back(self):
        self.source = self.root / 'contract.json'
        self.source.write_text('{}')
        with self.assertRaises(parser.ParseError) as failure:
            self.run_parse(Transport([]))
        self.assertEqual('unsupported_file_type', failure.exception.code)

    def test_fast_without_confirmed_endpoint_blocks(self):
        with self.assertRaises(parser.ParseError) as failure:
            self.run_parse(Transport([]), engine='pipeline')
        self.assertEqual('pipeline_not_configured', failure.exception.code)


if __name__ == '__main__':
    unittest.main()
