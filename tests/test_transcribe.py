"""Portable CLI contract tests; no model download or GPU needed."""
import contextlib
import dataclasses
import io
import json
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1] / 'skills' / 'complete-video-edit'

@dataclasses.dataclass
class Segment:
    start: float = 0.1
    end: float = 0.9
    text: str = '测试原声'
    words: tuple = ()

class ContractTests(unittest.TestCase):
    def invoke(self, segments, decode_error=False, no_vad=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        installed = root / 'installed-skill'
        shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns('__pycache__', 'models', '.venv', 'node_modules'))
        self.assertTrue((installed / 'requirements.lock.txt').is_file())
        source = root / 'input.wav'
        source.write_bytes(b'test fixture')
        output = root / 'result'
        calls = []
        class Model:
            def __init__(self, *a, **kw): pass
            def transcribe(self, audio, **kw):
                calls.append(kw)
                return iter(segments), types.SimpleNamespace(language='zh', duration=1)
        fw = types.ModuleType('faster_whisper')
        fw.WhisperModel = Model
        audio = types.ModuleType('faster_whisper.audio')
        def decode(*a, **kw):
            if decode_error: raise ValueError('corrupt media')
            return [0.0] * 16000
        audio.decode_audio = decode
        argv = ['transcribe.py', str(source), '--output', str(output), '--device', 'cpu']
        if no_vad: argv.append('--no-vad')
        code = 0
        with patch.dict(sys.modules, {'faster_whisper': fw, 'faster_whisper.audio': audio}), patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
            try: runpy.run_path(str(installed / 'scripts/transcribe.py'), run_name='__main__')
            except SystemExit as exc: code = exc.code
        return output, code, calls

    def test_installed_skill_creates_portable_draft_files(self):
        output, code, _ = self.invoke([Segment()])
        self.assertEqual(code, 0)
        self.assertEqual({p.name for p in output.iterdir()}, {'transcript.draft.txt', 'subtitles.draft.srt', 'transcript.json'})
        self.assertIn('待校对', (output / 'transcript.draft.txt').read_text(encoding='utf8'))
        srt = (output / 'subtitles.draft.srt').read_text(encoding='utf-8-sig')
        self.assertEqual(srt, '1\n00:00:00,100 --> 00:00:00,900\n测试原声\n')
        status = json.loads((output / 'transcript.json').read_text(encoding='utf8'))
        self.assertEqual(status['status'], 'transcribed')
        self.assertEqual(status['review_status'], 'automatic_unreviewed')

    def test_no_speech_is_success_with_review_instruction(self):
        output, code, _ = self.invoke([])
        self.assertEqual(code, 0)
        self.assertEqual([p.name for p in output.iterdir()], ['transcript.json'])
        state = json.loads((output / 'transcript.json').read_text(encoding='utf8'))
        self.assertEqual(state['status'], 'no_speech_detected')
        self.assertIn('visual', state['next_action'])

    def test_decode_error_is_not_no_speech(self):
        output, code, calls = self.invoke([], decode_error=True)
        self.assertNotEqual(code, 0)
        self.assertFalse(calls)
        self.assertEqual(json.loads((output / 'transcript.json').read_text(encoding='utf8'))['status'], 'decode_failed')

    def test_quiet_speech_retry_disables_vad(self):
        output, code, calls = self.invoke([Segment()], no_vad=True)
        self.assertEqual(code, 0)
        self.assertFalse(calls[0]['vad_filter'])
        self.assertFalse(json.loads((output / 'transcript.json').read_text(encoding='utf8'))['vad_enabled'])

if __name__ == '__main__': unittest.main()
