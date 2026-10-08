"""CLI credential configuration and fail-closed behavior for v2.5."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/document_parse_skill.py'


class ParserCLITest(unittest.TestCase):
    def run_cli(self, env, *args):
        clean = {k:v for k,v in os.environ.items() if not k.startswith(('DUMATE_', 'BAIDU_', 'QIANFAN_'))}
        clean.update(env)
        return subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), *args], env=clean,
            text=True, encoding='utf-8', capture_output=True, timeout=10)

    def test_missing_key_returns_actionable_link(self):
        result = self.run_cli({}, 'status')
        self.assertEqual(2, result.returncode)
        self.assertEqual('api_key_required', json.loads(result.stdout)['error'])
        self.assertIn('https://console.bce.baidu.com/qianfan/ais/console/apiKey', result.stdout)

    def test_explicit_key_file_is_read_without_disclosure(self):
        with tempfile.TemporaryDirectory() as temp:
            key = Path(temp) / 'key.txt'
            key.write_text('not-a-real-api-key', encoding='utf-8')
            result = self.run_cli({'QIANFAN_API_KEY_FILE': str(key)}, 'status')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(json.loads(result.stdout)['remote_verified'])
        self.assertNotIn('not-a-real-api-key', result.stdout + result.stderr)

    def test_newline_key_is_rejected_without_echo(self):
        result = self.run_cli({'QIANFAN_API_KEY': 'fake\r\nInjected: header'}, 'status')
        self.assertEqual(2, result.returncode)
        self.assertEqual('api_key_invalid', json.loads(result.stdout)['error'])
        self.assertNotIn('Injected', result.stdout)

    def test_old_dumate_session_is_not_an_alternate_auth(self):
        result = self.run_cli({'DUMATE_SESSION_ID': 'old', 'DUMATE_DTOKEN': 'old-token'}, 'route')
        self.assertEqual('api_key_required', json.loads(result.stdout)['error'])


if __name__ == '__main__':
    unittest.main()
