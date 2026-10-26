"""Decision validation and frame-aligned timeline contracts."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/complete-video-edit/scripts'
sys.path.insert(0, str(SCRIPTS))


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('editing'), 'editing package is missing')
        from editing import plan
        self.api = plan
        self.plan = {'schema_version': 1, 'source': '原片.mp4', 'cuts': [
            {'id': 'c1', 'start': 1, 'end': 2, 'reason': '同一句重启'}]}

    def test_complement_and_mapping(self):
        result = self.api.timeline(self.plan, 4, '25/1')
        self.assertEqual(result['expected_duration'], 3)
        self.assertEqual(result['expected_frames'], 75)
        self.assertEqual([(s['source_start'], s['source_end'], s['output_start'], s['output_end'])
                          for s in result['segments']], [(0, 1, 0, 1), (2, 4, 1, 3)])

    def test_empty_cuts_preserve_everything(self):
        self.plan['cuts'] = []
        self.assertEqual(self.api.timeline(self.plan, 4, '30000/1001')['expected_frames'], 120)

    def test_quantization_records_effective_cuts(self):
        self.plan['cuts'][0].update(start=1.01, end=2.01)
        result = self.api.timeline(self.plan, 4, '25/1')
        self.assertEqual(result['cuts'][0]['effective_start'], 1.04)
        self.assertEqual(result['cuts'][0]['effective_end'], 2.04)
        self.assertEqual(self.plan['cuts'][0]['start'], 1.01)

    def test_adjacent_cuts_are_legal(self):
        self.plan['cuts'].append({'id': 'c2', 'start': 2, 'end': 3, 'reason': '重复'})
        self.assertEqual(self.api.timeline(self.plan, 4, '25')['expected_duration'], 2)

    def test_rejects_bad_schema_and_intervals(self):
        cases = []
        for key, value in [('schema_version', True), ('schema_version', 2), ('source', ''),
                           ('source', 3), ('cuts', {}), ('overlays', []), ('speed', 1),
                           ('source_sha256', 'wrong'), ('audio_stream', True), ('audio_stream', -1)]:
            p = copy.deepcopy(self.plan)
            p[key] = value
            cases.append(p)
        for key, value in [('start', True), ('start', '1'), ('start', float('nan')),
                           ('end', float('inf')), ('start', -1), ('end', 1), ('end', 5),
                           ('reason', '  '), ('reason', 42), ('id', ''), ('speed', 1)]:
            p = copy.deepcopy(self.plan)
            p['cuts'][0][key] = value
            cases.append(p)
        for cut in [dict(self.plan['cuts'][0]), {'id': 'c2', 'start': 0, 'end': .5, 'reason': 'x'},
                    {'id': 'c2', 'start': 1.5, 'end': 3, 'reason': 'x'}]:
            p = copy.deepcopy(self.plan)
            p['cuts'].append(cut)
            cases.append(p)
        p = copy.deepcopy(self.plan)
        p['cuts'][0].update(start=0, end=4)
        cases.append(p)
        for p in cases:
            with self.subTest(p=p), self.assertRaises(ValueError):
                self.api.timeline(p, 4, '25')

    def test_subframe_deletion_is_not_silently_ignored(self):
        self.plan['cuts'][0].update(start=1.001, end=1.002)
        with self.assertRaisesRegex(ValueError, 'frame'):
            self.api.timeline(self.plan, 4, '25')

    def test_source_resolution_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'plan.json'
            path.write_text(json.dumps(self.plan), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'source'):
                self.api.load_plan(path)
            (root / '原片.mp4').write_bytes(b'fixture')
            data, source = self.api.load_plan(path)
            self.assertEqual(source, root / '原片.mp4')
            self.assertEqual(data, self.plan)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.json'
            path.write_text('{"schema_version":1,"schema_version":2}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                self.api.load_plan(path)


if __name__ == '__main__':
    unittest.main()
