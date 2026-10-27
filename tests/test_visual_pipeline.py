"""Short real-media smoke test; Remotion rendering is opt-in for relevant CI changes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1] / 'skills/complete-video-edit'
FFMPEG, FFPROBE = shutil.which('ffmpeg'), shutil.which('ffprobe')


@unittest.skipUnless(FFMPEG and FFPROBE, 'FFmpeg/FFprobe required')
class VisualPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=320x240:r=25:d=3',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=3',
                        '-c:v', 'libx264', '-c:a', 'aac', str(cls.source)], capture_output=True, check=True)
        for name, color, size in [('one', 'red', '120x80'), ('two', 'blue', '80x120')]:
            subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s={size}',
                            '-frames:v', '1', '-threads', '1', str(cls.root / f'{name}.png')],
                           capture_output=True, check=True)
        plan = cls.root / 'edit.json'
        plan.write_text(json.dumps({'schema_version': 1, 'source': str(cls.source), 'cuts': []}), encoding='utf-8')
        cls.master = cls.root / 'master'
        subprocess.run([sys.executable, str(SKILL / 'scripts/edit.py'), 'render', str(plan),
                        '--output', str(cls.master)], capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(dir=self.root))
        self.plan = self.work / 'visual.json'
        self.plan.write_text(json.dumps({'schema_version': 1, 'edit_result': str(self.master), 'effects': [
            {'id': 'pair', 'type': 'photo-pair', 'timebase': 'output', 'start_frame': 10,
             'duration_frames': 55, 'transition_frames': 5,
             'photos': [str(self.root / 'one.png'), str(self.root / 'two.png')]}]}), encoding='utf-8')
        self.workspace = self.work / 'workspace'

    def invoke(self, *args, success=True, skill=SKILL):
        result = subprocess.run([sys.executable, str(skill / 'scripts/visual.py'), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail('Expected JSON response: ' + result.stdout + result.stderr)

    def test_portable_prepare_preserves_master_and_rejects_reuse(self):
        installed = self.work / 'installed'
        shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns('node_modules', '__pycache__', '.venv', 'models'))
        before = (self.master / 'verification.json').read_bytes()
        self.invoke('prepare', self.plan, '--output', self.workspace, skill=installed)
        self.assertEqual(before, (self.master / 'verification.json').read_bytes())
        props = json.loads((self.workspace / 'props.json').read_text(encoding='utf-8'))
        self.assertEqual(props['durationInFrames'], 75)
        self.assertEqual(props['effects'][0]['startFrame'], 10)
        self.assertTrue((self.workspace / 'public/master.mp4').is_file())
        self.invoke('prepare', self.plan, '--output', self.workspace, success=False)

    def test_modified_staged_inputs_rejected_before_render(self):
        self.invoke('prepare', self.plan, '--output', self.workspace)
        (self.workspace / 'props.json').write_text('{}', encoding='utf-8')
        self.invoke('render', self.workspace, '--output', self.work / 'result', success=False)
        self.assertFalse((self.work / 'result/output.mp4').exists())

    def test_unreadable_photo_fails_during_prepare(self):
        broken = self.work / 'broken.png'
        broken.write_bytes(b'not an image')
        data = json.loads(self.plan.read_text(encoding='utf-8'))
        data['effects'][0]['photos'][0] = str(broken)
        self.plan.write_text(json.dumps(data), encoding='utf-8')
        self.invoke('prepare', self.plan, '--output', self.workspace, success=False)
        record = json.loads((self.workspace / 'workspace.json').read_text(encoding='utf-8'))
        self.assertEqual(record['status'], 'failed')

    @unittest.skipUnless(os.environ.get('RUN_REMOTION_SMOKE') == '1', 'optional Remotion smoke test')
    def test_full_preview_stills_and_audio(self):
        self.invoke('prepare', self.plan, '--output', self.workspace)
        result = self.work / 'full'
        self.invoke('render', self.workspace, '--output', result, '--stills')
        report = json.loads((result / 'verification.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'passed')
        self.assertTrue(report['checks']['original_audio_payload'])
        self.assertEqual(report['actual']['frames'], 75)
        self.assertGreaterEqual(len(list((result / 'stills').glob('*.png'))), 5)
        # First focus is red, second focus blue; a frame after the effect is green.
        for frame, channel in [(35, 0), (55, 2), (70, 1)]:
            raw = subprocess.check_output([FFMPEG, '-v', 'error', '-i', str(result / 'output.mp4'),
                                           '-vf', f'select=eq(n\\,{frame}),crop=2:2:159:119',
                                           '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
            self.assertEqual(max(range(3), key=lambda c: raw[c]), channel)
        preview = self.work / 'preview'
        self.invoke('render', self.workspace, '--output', preview, '--start-frame', 20, '--end-frame', 60)
        record = json.loads((preview / 'run.json').read_text(encoding='utf-8'))
        self.assertEqual(record['audio_mode'], 'trimmed_preview_aac')
        self.assertEqual(record['frame_range'], [20, 60])
        report = json.loads((preview / 'verification.json').read_text(encoding='utf-8'))
        self.assertEqual(report['actual']['frames'], 40)

    @unittest.skipUnless(os.environ.get('RUN_REMOTION_SMOKE') == '1', 'optional Remotion smoke test')
    def test_single_styles_geometry_audio_and_preview(self):
        def pixels(path, width, height, frame=None):
            cmd = [FFMPEG, '-v', 'error', '-i', str(path)]
            if frame is not None:
                cmd += ['-vf', f'select=eq(n\\,{frame})']
            return subprocess.check_output(cmd + ['-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])

        def bounds(raw, width, channel):
            points = [(i // 3 % width, i // 3 // width) for i in range(0, len(raw), 3)
                      if raw[i + channel] > 100 and raw[i + channel] > 2 * max(raw[i + (channel + 1) % 3], raw[i + (channel + 2) % 3])]
            self.assertTrue(points, 'photo must actually be visible')
            return tuple(f(p[n] for p in points) for n, f in ((0, min), (1, min), (0, max), (1, max)))

        for width, height in ((320, 240), (240, 320)):
            with self.subTest(canvas=(width, height)):
                directory = self.work / f'{width}x{height}'
                directory.mkdir()
                master = self.master
                if height > width:
                    source = directory / 'portrait.mp4'
                    subprocess.run([FFMPEG, '-v', 'error', '-i', str(self.source), '-vf', 'transpose=1',
                                    '-c:v', 'libx264', '-c:a', 'copy', str(source)], check=True, capture_output=True)
                    edit = directory / 'edit.json'
                    edit.write_text(json.dumps({'schema_version': 1, 'source': str(source), 'cuts': []}), encoding='utf-8')
                    master = directory / 'master'
                    subprocess.run([sys.executable, str(SKILL / 'scripts/edit.py'), 'render', str(edit),
                                    '--output', str(master)], check=True, capture_output=True)
                effects = []
                for start, options in [(5, {}), (25, {'motion': 'ken-burns', 'zoom_factor': 1.2}),
                                       (45, {'layout': 'pip', 'position': 'top-right', 'scale': .3})]:
                    effects.append({'id': f'single-{start}', 'type': 'photo-single', 'timebase': 'output',
                                    'start_frame': start, 'duration_frames': 15, 'entry_frames': 2, 'exit_frames': 2,
                                    'photos': [str(self.root / ('two.png' if start == 45 else 'one.png'))], **options})
                plan = directory / 'visual.json'
                plan.write_text(json.dumps({'schema_version': 1, 'edit_result': str(master), 'effects': effects}), encoding='utf-8')
                workspace, full = directory / 'workspace', directory / 'full'
                self.invoke('prepare', plan, '--output', workspace)
                self.invoke('render', workspace, '--output', full, '--stills')
                report = json.loads((full / 'verification.json').read_text(encoding='utf-8'))
                self.assertTrue(report['checks']['original_audio_payload'])
                self.assertEqual(report['actual']['frames'], 75)
                for frame in (5, 19, 20, 39, 40, 59, 60, 74):
                    raw = pixels(full / 'output.mp4', width, height, frame)
                    center = 3 * ((height // 2) * width + width // 2)
                    self.assertGreater(raw[center + 1], 2 * max(raw[center], raw[center + 2]))
                fade = bounds(pixels(full / 'stills/frame-000012.png', width, height), width, 0)
                early = bounds(pixels(full / 'stills/frame-000027.png', width, height), width, 0)
                late = bounds(pixels(full / 'stills/frame-000037.png', width, height), width, 0)
                self.assertGreater(late[2] - late[0], early[2] - early[0])
                for box in (fade, early, late):
                    self.assertTrue(0 < box[0] < box[2] < width - 1)
                    self.assertTrue(0 < box[1] < box[3] < height - 1)
                    self.assertAlmostEqual((box[2] - box[0] + 1) / (box[3] - box[1] + 1), 1.5, delta=.04)
                raw = pixels(full / 'stills/frame-000052.png', width, height)
                pip = bounds(raw, width, 2)
                self.assertAlmostEqual((pip[2] - pip[0] + 1) / (pip[3] - pip[1] + 1), 2 / 3, delta=.04)
                self.assertGreaterEqual(pip[0], int(width * .66) - 1)
                self.assertGreaterEqual(pip[1], int(height * .04) - 1)
                self.assertLessEqual(pip[2], int(width * .96) + 1)
                self.assertLessEqual(pip[3], int(height * .34) + 1)
                # PiP must not dim or cover the center of the master.
                clean = pixels(full / 'stills/frame-000060.png', width, height)
                center = 3 * ((height // 2) * width + width // 2)
                self.assertEqual(raw[center:center + 3], clean[center:center + 3])
                if width > height:
                    preview = directory / 'preview'
                    self.invoke('render', workspace, '--output', preview, '--start-frame', 31, '--end-frame', 41, '--stills')
                    self.assertEqual(pixels(full / 'stills/frame-000032.png', width, height),
                                     pixels(preview / 'stills/frame-000032.png', width, height))
                    preview_report = json.loads((preview / 'verification.json').read_text(encoding='utf-8'))
                    self.assertEqual(preview_report['actual']['frames'], 10)

    @unittest.skipUnless(os.environ.get('RUN_REMOTION_SMOKE') == '1', 'optional Remotion smoke test')
    def test_silent_fractional_frame_rate_master(self):
        source = self.work / 'silent.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-i', str(self.source), '-an', '-r', '30000/1001',
                        '-c:v', 'libx264', str(source)], capture_output=True, check=True)
        edit = self.work / 'edit.json'
        edit.write_text(json.dumps({'schema_version': 1, 'source': str(source), 'cuts': []}), encoding='utf-8')
        master = self.work / 'silent-master'
        subprocess.run([sys.executable, str(SKILL / 'scripts/edit.py'), 'render', str(edit), '--output', str(master)],
                       capture_output=True, check=True)
        data = json.loads(self.plan.read_text(encoding='utf-8'))
        data['edit_result'] = str(master)
        self.plan.write_text(json.dumps(data), encoding='utf-8')
        self.invoke('prepare', self.plan, '--output', self.workspace)
        result = self.work / 'full'
        self.invoke('render', self.workspace, '--output', result)
        report = json.loads((result / 'verification.json').read_text(encoding='utf-8'))
        self.assertFalse(report['actual']['has_audio'])
        self.assertEqual(report['actual']['fps'], '30000/1001')


if __name__ == '__main__':
    unittest.main()
