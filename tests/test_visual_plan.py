"""Frame mapping is shared with the edit result; effects never invent a new timeline."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/complete-video-edit/scripts'))


class VisualPlanTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('editing.visual_plan'), 'visual plan module missing')
        from editing.visual_plan import resolve_plan
        self.resolve = resolve_plan
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('one.png', 'two.png'):
            (self.root / name).write_bytes(b'photo fixture')
        self.mapping = {'fps': '25', 'expected_frames': 150, 'segments': [
            {'source_start_frame': 0, 'source_end_frame': 50, 'output_start_frame': 0, 'output_end_frame': 50},
            {'source_start_frame': 100, 'source_end_frame': 200, 'output_start_frame': 50, 'output_end_frame': 150}]}
        self.data = {'schema_version': 1, 'edit_result': 'master', 'effects': [
            {'id': 'photos', 'type': 'photo-pair', 'photos': ['one.png', 'two.png'],
             'timebase': 'source', 'start_frame': 110, 'duration_frames': 50}]}

    def test_source_anchor_maps_to_output_frames(self):
        effects = self.resolve(self.data, self.root, self.mapping)
        self.assertEqual(effects[0]['startFrame'], 60)
        self.assertEqual(effects[0]['durationInFrames'], 50)
        self.assertEqual(sum(effects[0]['phaseFrames']), 50)
        self.assertEqual(self.data['effects'][0]['start_frame'], 110)

    def test_output_anchor_unchanged(self):
        self.data['effects'][0].update(timebase='output', start_frame=50)
        self.assertEqual(self.resolve(self.data, self.root, self.mapping)[0]['startFrame'], 50)

    def test_deleted_or_cross_cut_source_anchor_rejected(self):
        for start in (40, 60):
            self.data['effects'][0]['start_frame'] = start
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, 'retained segment'):
                self.resolve(self.data, self.root, self.mapping)

    def test_bad_props_and_missing_assets(self):
        for key, value in [('type', 'caption'), ('duration_frames', 4), ('start_frame', True),
                           ('timebase', 'guess'), ('photos', ['missing.png', 'two.png']),
                           ('photos', ['one.png']), ('speed', 1), ('transition_frames', 20),
                           ('overview_scale', .8), ('focus_scale', 1.1), ('layer', -1)]:
            data = copy.deepcopy(self.data)
            data['effects'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.resolve(data, self.root, self.mapping)

    def single(self, **options):
        effect = self.data['effects'][0]
        effect.update(type='photo-single', photos=['one.png'], **options)
        return effect

    def test_single_defaults_mapping_and_shortest_window(self):
        effect = self.single()
        result = self.resolve(self.data, self.root, self.mapping)[0]
        self.assertEqual((result['type'], result['layout'], result['motion']), ('photo-single', 'center', 'none'))
        self.assertEqual(result['startFrame'], 60)
        self.assertEqual(len(result['photos']), 1)
        self.assertEqual(result['scale'], .88)
        effect.update(duration_frames=3)
        result = self.resolve(self.data, self.root, self.mapping)[0]
        self.assertEqual((result['entryFrames'], result['exitFrames']), (1, 1))
        self.assertIn(1, result['reviewFrames'])
        self.assertIn(3, result['reviewFrames'])

    def test_single_layout_and_motion_validation(self):
        self.single()
        base = copy.deepcopy(self.data)
        for options in ({'photos': ['one.png', 'two.png']}, {'layout': 'guess'}, {'motion': 'slide-in'},
                        {'duration_frames': 2}, {'entry_frames': 30, 'exit_frames': 20},
                        {'entry_frames': True}, {'exit_frames': 0}, {'scale': 1.1},
                        {'position': 'top-left'}, {'margin': .1}, {'zoom_factor': 1.1},
                        {'motion': 'ken-burns', 'zoom_factor': 1},
                        {'motion': 'ken-burns', 'zoom_factor': float('nan')},
                        {'layout': 'pip', 'position': 'center'}, {'layout': 'pip', 'scale': .9},
                        {'layout': 'pip', 'margin': -.1}, {'transition_frames': 2}):
            data = copy.deepcopy(base)
            data['effects'][0].update(options)
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.resolve(data, self.root, self.mapping)
        self.data['effects'][0].update(layout='pip', position='top-left', motion='ken-burns')
        result = self.resolve(self.data, self.root, self.mapping)[0]
        self.assertEqual((result['position'], result['scale'], result['zoomFactor']), ('top-left', .3, 1.08))
        self.data['effects'][0]['start_frame'] = 40
        with self.assertRaisesRegex(ValueError, 'retained segment'):
            self.resolve(self.data, self.root, self.mapping)

    def test_pair_keeps_old_values_and_rejects_single_options(self):
        result = self.resolve(self.data, self.root, self.mapping)[0]
        self.assertEqual(result['phaseFrames'], [11, 2, 11, 2, 11, 2, 11])
        self.assertEqual((result['overviewScale'], result['focusScale']), (.36, .88))
        self.data['effects'][0]['motion'] = 'ken-burns'
        with self.assertRaises(ValueError):
            self.resolve(self.data, self.root, self.mapping)

    def test_overlap_or_unknown_fields_rejected(self):
        other = copy.deepcopy(self.data['effects'][0])
        other['id'] = 'other'
        self.data['effects'].append(other)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            self.resolve(self.data, self.root, self.mapping)
        self.data['effects'].pop()
        self.data['music'] = 'something'
        with self.assertRaises(ValueError):
            self.resolve(self.data, self.root, self.mapping)


if __name__ == '__main__':
    unittest.main()
