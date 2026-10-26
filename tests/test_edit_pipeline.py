"""Real FFmpeg contracts, including selected picture and sound content."""
from array import array
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1] / 'skills/complete-video-edit'
FFMPEG, FFPROBE = shutil.which('ffmpeg'), shutil.which('ffprobe')


@unittest.skipUnless(FFMPEG and FFPROBE, 'FFmpeg and FFprobe are required')
class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.installed = cls.root / 'installed skill'
        shutil.copytree(SKILL, cls.installed, ignore=shutil.ignore_patterns('__pycache__', '.venv', 'models'))
        cls.source = cls.root / '原片 with spaces.mkv'
        # Three one-second pictures and tones, exactly 75 video frames.
        graph = ('[0:v][1:v][2:v]concat=n=3:v=1:a=0[v];'
                 '[3:a][4:a][5:a]concat=n=3:v=0:a=1[a]')
        cmd = [FFMPEG, '-v', 'error', '-nostdin']
        for color in ('red', 'green', 'blue'):
            cmd += ['-f', 'lavfi', '-i', f'color=c={color}:s=160x120:r=25:d=1']
        for freq in (440, 660, 880):
            cmd += ['-f', 'lavfi', '-i', f'sine=frequency={freq}:sample_rate=48000:duration=1']
        cmd += ['-filter_complex_threads', '1', '-filter_complex', graph,
                '-map', '[v]', '-map', '[a]', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', str(cls.source)]
        subprocess.run(cmd, capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(dir=self.root))
        self.plan = self.work / 'plan.json'
        self.data = {'schema_version': 1, 'source': str(self.source), 'cuts': [
            {'id': 'middle', 'start': 1, 'end': 2, 'reason': '测试：删除绿色中段'}]}
        self.output = self.work / 'result'

    def invoke(self, *args, success=True):
        result = subprocess.run([sys.executable, str(self.installed / 'scripts/edit.py'), *map(str, args)],
                                cwd=self.work, capture_output=True, text=True, encoding='utf-8')
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f'CLI must return JSON even on failure: {result.stdout} {result.stderr}')

    def write_plan(self):
        self.plan.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')

    def render(self, *extra):
        self.write_plan()
        return self.invoke('render', self.plan, '--output', self.output, *extra)

    def picture(self, path, t):
        out = subprocess.check_output([FFMPEG, '-v', 'error', '-ss', str(t), '-i', str(path),
                                       '-frames:v', '1', '-vf', 'scale=1:1', '-pix_fmt', 'rgb24',
                                       '-f', 'rawvideo', '-'])
        return tuple(out)

    def audio(self, path, t, duration=.2):
        raw = subprocess.check_output([FFMPEG, '-v', 'error', '-ss', str(t), '-i', str(path),
                                       '-t', str(duration), '-vn', '-ac', '1', '-ar', '48000',
                                       '-f', 's16le', '-'])
        samples = array('h', raw)
        if sys.byteorder != 'little':
            samples.byteswap()
        return samples

    def frequency(self, path, t):
        samples = self.audio(path, t)
        return sum(a <= 0 < b for a, b in zip(samples, samples[1:])) / (len(samples) / 48000)

    def test_portable_render_preserves_selected_picture_sound_and_order(self):
        result = self.render()
        self.assertEqual(result['status'], 'verified')
        media = self.output / 'output.mp4'
        self.assertEqual(max(range(3), key=self.picture(media, .5).__getitem__), 0)
        self.assertEqual(max(range(3), key=self.picture(media, 1.5).__getitem__), 2)
        self.assertAlmostEqual(self.frequency(media, .5), 440, delta=10)
        self.assertAlmostEqual(self.frequency(media, 1.5), 880, delta=10)
        run = json.loads((self.output / 'run.json').read_text(encoding='utf-8'))
        self.assertTrue(run['commands'])
        self.assertEqual(run['source_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(run['review_status'], 'pending_human_review')
        report = self.invoke('verify', self.output)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['actual']['frames'], 50)
        self.assertFalse((self.output / 'output.partial.mp4').exists())

    def test_silent_source_and_non_frame_boundaries(self):
        source = self.work / 'silent.mkv'
        subprocess.run([FFMPEG, '-v', 'error', '-i', str(self.source), '-map', '0:v:0',
                        '-c', 'copy', str(source)], capture_output=True, check=True)
        self.data['source'] = str(source)
        self.data['cuts'][0].update(start=1.01, end=2.01)
        self.render()
        report = self.invoke('verify', self.output)
        self.assertFalse(report['actual']['has_audio'])
        self.assertEqual(report['actual']['frames'], 50)
        mapping = json.loads((self.output / 'timeline.json').read_text(encoding='utf-8'))
        self.assertEqual(mapping['cuts'][0]['effective_start'], 1.04)

    def test_empty_cuts_and_head_tail_cuts(self):
        self.data['cuts'] = []
        self.render()
        self.assertEqual(self.invoke('verify', self.output)['actual']['frames'], 75)
        self.output = self.work / 'trimmed'
        self.data['cuts'] = [{'id': 'head', 'start': 0, 'end': .4, 'reason': '测试'},
                             {'id': 'tail', 'start': 2.6, 'end': 3, 'reason': '测试'}]
        self.render()
        self.assertEqual(self.invoke('verify', self.output)['actual']['frames'], 55)

    def test_existing_directory_and_changed_source_rejected(self):
        self.write_plan()
        self.output.mkdir()
        marker = self.output / 'keep.txt'
        marker.write_text('unchanged')
        self.invoke('render', self.plan, '--output', self.output, success=False)
        self.assertEqual(marker.read_text(), 'unchanged')
        self.data['source_sha256'] = '0' * 64
        self.write_plan()
        self.invoke('check', self.plan, success=False)

    def test_reverification_rejects_substituted_media(self):
        self.render()
        shutil.copyfile(self.source, self.output / 'output.mp4')
        report = self.invoke('verify', self.output, success=False)
        self.assertEqual(report['status'], 'failed')
        saved = json.loads((self.output / 'verification.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['status'], 'failed')

    def test_failed_encoder_never_publishes_final(self):
        self.write_plan()
        # Python answers -version but rejects FFmpeg flags: portable failing executable.
        self.invoke('render', self.plan, '--output', self.output,
                    '--ffmpeg', sys.executable, success=False)
        self.assertFalse((self.output / 'output.mp4').exists())
        record = json.loads((self.output / 'run.json').read_text(encoding='utf-8'))
        self.assertEqual(record['status'], 'failed')
        self.assertTrue(record['error'])

    def test_malformed_plan_is_machine_readable(self):
        self.plan.write_text('{bad json', encoding='utf-8')
        self.assertEqual(self.invoke('check', self.plan, success=False)['status'], 'failed')

    def test_delayed_audio_keeps_original_offset(self):
        source = self.work / 'delayed.mkv'
        subprocess.run([FFMPEG, '-v', 'error', '-i', str(self.source), '-itsoffset', '0.4',
                        '-i', str(self.source), '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy',
                        str(source)], capture_output=True, check=True)
        self.data['source'] = str(source)
        self.data['cuts'] = []
        self.render()
        media = self.output / 'output.mp4'
        samples = self.audio(media, .05)
        self.assertLess(max(abs(x) for x in samples), 100)
        self.assertAlmostEqual(self.frequency(media, .65), 440, delta=10)

    def test_fractional_frame_rate_many_cuts(self):
        source = self.work / 'fractional.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-i', str(self.source), '-r', '30000/1001',
                        '-c:v', 'libx264', '-c:a', 'aac', str(source)], capture_output=True, check=True)
        self.data['source'] = str(source)
        self.data['cuts'] = [{'id': str(i), 'start': round(.1 + i * .15, 3),
                              'end': round(.15 + i * .15, 3), 'reason': '测试'} for i in range(18)]
        self.render()
        report = self.invoke('verify', self.output)
        self.assertEqual(report['actual']['fps'], '30000/1001')

    def test_nonzero_source_timestamp(self):
        source = self.work / 'offset.mkv'
        subprocess.run([FFMPEG, '-v', 'error', '-itsoffset', '5', '-i', str(self.source),
                        '-c', 'copy', '-copyts', str(source)], capture_output=True, check=True)
        self.data['source'] = str(source)
        self.render()
        self.assertAlmostEqual(self.frequency(self.output / 'output.mp4', 1.5), 880, delta=10)

    def test_no_cut_does_not_add_frame_from_rounded_duration(self):
        for ext in ('mp4', 'mkv'):
            source = self.work / f'fifty.{ext}'
            subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=red:s=160x120:r=30', '-frames:v', '50', '-c:v', 'libx264',
                            str(source)], capture_output=True, check=True)
            self.data.update(source=str(source), cuts=[])
            self.output = self.work / f'result-{ext}'
            self.render()
            self.assertEqual(self.invoke('verify', self.output)['actual']['frames'], 50)

    def test_failed_reverification_replaces_old_success_report(self):
        self.render()
        self.invoke('verify', self.output, '--ffmpeg', str(self.work / 'missing'), success=False)
        report = json.loads((self.output / 'verification.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'failed')

    def test_changed_audit_plan_is_detected(self):
        self.render()
        (self.output / 'plan.json').write_text('{}', encoding='utf-8')
        report = self.invoke('verify', self.output, success=False)
        self.assertEqual(report['status'], 'failed')

    def test_invalid_run_record_replaces_old_success_report(self):
        self.render()
        (self.output / 'run.json').write_text('[]', encoding='utf-8')
        self.invoke('verify', self.output, success=False)
        report = json.loads((self.output / 'verification.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
