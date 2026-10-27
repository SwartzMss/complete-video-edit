"""CLI contracts for portable, read-only asset diagnostics."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1] / 'skills/complete-video-edit'
SCRIPT = SKILL / 'scripts/check_assets.py'


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'assets/example'
        self.package.mkdir(parents=True)
        self.media = self.package / 'tone.wav'
        self.media.write_bytes((SKILL / 'assets/tv-color-bars/beep.wav').read_bytes())
        self.data = {'schema_version': 1, 'asset_id': 'example', 'name': 'Example',
                     'kind': 'audio', 'description': 'Test tone', 'usage': ['Optional tone'],
                     'files': [{'file_id': 'tone', 'path': 'tone.wav', 'kind': 'audio',
                                'role': 'sound', 'storage': 'bundled', 'requires': ['ffmpeg'],
                                'sha256': hashlib.sha256(self.media.read_bytes()).hexdigest(),
                                'source': {'url': None, 'description': 'Locally synthesized'},
                                'rights': {'license': 'unknown', 'redistribution': 'unknown',
                                           'notes': 'No license declaration recorded'}}]}

    def run_check(self, *args, code=0, script=SCRIPT):
        (self.package / 'manifest.json').write_text(json.dumps(self.data), encoding='utf-8')
        result = subprocess.run([sys.executable, str(script), '--root', str(self.root / 'assets'),
                                 '--json', *args], cwd=self.root, capture_output=True,
                                text=True, encoding='utf-8')
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_missing_probe_is_not_corruption_and_rights_are_independent(self):
        report = self.run_check('--ffprobe', str(self.root / 'no-probe'))
        item = report['assets'][0]['files'][0]
        self.assertEqual(item['existence'], 'present')
        self.assertEqual(item['hash']['status'], 'matched')
        self.assertEqual(item['probe']['status'], 'tool_missing')
        self.assertEqual(item['rights']['redistribution'], 'unknown')
        self.assertEqual(item['browser_preview'], 'not_checked')
        self.assertEqual(item['render'], 'not_checked')
        self.assertEqual(report['summary']['errors'], 0)

    def test_missing_local_vs_bundled(self):
        self.media.unlink()
        report = self.run_check(code=1)
        self.assertEqual(report['assets'][0]['files'][0]['existence'], 'missing')
        self.data['files'][0]['storage'] = 'local_only'
        report = self.run_check()
        self.assertEqual(report['summary']['errors'], 0)
        self.assertIn('local_file_missing', [i['code'] for i in report['assets'][0]['files'][0]['issues']])

    def test_hash_mismatch_does_not_modify_files(self):
        self.media.write_bytes(b'changed media')
        before = self.media.read_bytes()
        report = self.run_check('--decode', code=1)
        item = report['assets'][0]['files'][0]
        self.assertEqual(item['hash']['status'], 'mismatch')
        self.assertEqual(item['decode']['status'], 'not_checked')
        self.assertEqual(self.media.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.package.iterdir()), ['manifest.json', 'tone.wav'])

    def test_invalid_schema_paths_and_duplicate_ids(self):
        original = json.loads(json.dumps(self.data))
        for path in ('../tone.wav', '/tmp/tone.wav', 'C:/tone.wav', '..\\tone.wav', 'https://example.com/a'):
            with self.subTest(path=path):
                self.data['files'][0]['path'] = path
                self.assertEqual(self.run_check(code=1)['assets'][0]['manifest_status'], 'invalid')
        self.data = original
        self.data['files'].append(dict(self.data['files'][0]))
        self.assertEqual(self.run_check(code=1)['assets'][0]['manifest_status'], 'invalid')
        self.data = {'schema_version': True}
        self.assertEqual(self.run_check(code=1)['assets'][0]['manifest_status'], 'invalid')

    def test_corrupt_media_and_missing_decode_tool_are_distinct(self):
        if not shutil.which('ffprobe'):
            self.skipTest('FFprobe required')
        report = self.run_check('--decode', '--ffmpeg', str(self.root / 'missing'))
        item = report['assets'][0]['files'][0]
        self.assertEqual(item['probe']['status'], 'passed')
        self.assertEqual(item['decode']['status'], 'tool_missing')
        self.assertEqual(item['dependencies']['ffmpeg'], 'missing')
        self.media.write_bytes(b'not media')
        self.data['files'][0].pop('sha256')
        report = self.run_check(code=1)
        self.assertEqual(report['assets'][0]['files'][0]['probe']['status'], 'failed')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'media tools required')
    def test_real_probe_and_sample_decode(self):
        before = self.media.read_bytes()
        report = self.run_check('--decode')
        item = report['assets'][0]['files'][0]
        self.assertEqual(item['probe']['status'], 'passed')
        self.assertEqual(item['probe']['streams'][0]['codec_name'], 'pcm_s16le')
        self.assertEqual(item['decode']['status'], 'sample_passed')
        self.assertEqual(item['render'], 'not_checked')
        self.assertEqual(self.media.read_bytes(), before)

    def test_invalid_manifest_does_not_hide_other_assets(self):
        broken = self.root / 'assets/broken'
        broken.mkdir()
        (broken / 'manifest.json').write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
        report = self.run_check(code=1)
        self.assertEqual(len(report['assets']), 2)
        self.assertEqual(report['assets'][0]['manifest_status'], 'invalid')
        self.assertEqual(report['assets'][1]['manifest_status'], 'valid')
        (broken / 'manifest.json').write_text(json.dumps(self.data), encoding='utf-8')
        report = self.run_check(code=1)
        self.assertTrue(any('duplicate asset_id' in i['message'] for a in report['assets'] for i in a['issues']))

    def test_symlink_escape_rejected(self):
        outside = self.root / 'outside.wav'
        outside.write_bytes(self.media.read_bytes())
        link = self.package / 'link.wav'
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest('symlinks not permitted on this host')
        self.data['files'][0]['path'] = 'link.wav'
        self.assertEqual(self.run_check(code=1)['assets'][0]['manifest_status'], 'invalid')

    def test_extreme_metadata_is_reported_without_crashing(self):
        self.data['files'][0]['metadata'] = {'duration_seconds': 10 ** 400}
        self.assertEqual(self.run_check(code=1)['assets'][0]['manifest_status'], 'invalid')

    def test_malformed_probe_output_stays_in_report(self):
        self.run_check('--ffprobe', str(self.root / 'missing'))
        spec = importlib.util.spec_from_file_location('asset_inventory', SKILL / 'scripts/asset_inventory.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for output in ('null', '{"streams":null}', '{"streams":[null]}'):
            with self.subTest(output=output), patch.object(module, 'run', return_value=output):
                report = module.inventory(self.root / 'assets', ffprobe=sys.executable)
                self.assertEqual(report['assets'][0]['files'][0]['probe']['status'], 'failed')
                self.assertGreater(report['summary']['errors'], 0)

    def test_json_output_is_utf8_on_non_utf8_hosts(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--json'], capture_output=True,
                                env={**os.environ, 'PYTHONIOENCODING': 'ascii'})
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        report = json.loads(result.stdout.decode('utf-8'))
        self.assertTrue(any('彩色' in a['name'] for a in report['assets']))

    def test_installed_skill_default_root_and_repository_manifests(self):
        installed = self.root / 'installed'
        shutil.copytree(SKILL / 'scripts', installed / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(SKILL / 'assets', installed / 'assets')
        result = subprocess.run([sys.executable, str(installed / 'scripts/check_assets.py'), '--json'],
                                cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        assets = {a['asset_id']: a for a in report['assets']}
        self.assertEqual(len(assets['tv-color-bars']['files']), 2)
        self.assertEqual(assets['boonie-bears-outro']['files'][0]['existence'], 'missing')
        self.assertTrue(all(f['hash']['status'] == 'matched' for f in assets['tv-color-bars']['files']))


if __name__ == '__main__':
    unittest.main()
