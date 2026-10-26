"""Explicit media support boundaries, without requiring FFmpeg."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/complete-video-edit/scripts'))
from editing.media import inspect_source


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.info = {'streams': [
            {'index': 0, 'codec_type': 'video', 'width': 160, 'height': 120,
             'pix_fmt': 'yuv420p', 'sample_aspect_ratio': '1:1', 'r_frame_rate': '25/1',
             'duration': '3', 'start_time': '0'},
            {'index': 1, 'codec_type': 'audio', 'channels': 1}], 'format': {'duration': '4'}}

    def test_video_duration_not_longer_audio_duration(self):
        self.assertEqual(inspect_source(self.info, {})['duration'], 3)

    def test_explicit_multitrack_selection(self):
        self.info['streams'].append({'index': 2, 'codec_type': 'audio', 'channels': 2})
        with self.assertRaisesRegex(ValueError, 'multiple audio'):
            inspect_source(self.info, {})
        self.assertEqual(inspect_source(self.info, {'audio_stream': 2})['channels'], 2)
        with self.assertRaises(ValueError):
            inspect_source(self.info, {'audio_stream': 0})

    def test_unsupported_media_fails_clearly(self):
        for field, value in [('tags', {'rotate': '90'}), ('side_data_list', [{'rotation': -90}]),
                             ('pix_fmt', 'yuv420p10le'), ('color_transfer', 'arib-std-b67'),
                             ('sample_aspect_ratio', '4:3'), ('field_order', 'tt'),
                             ('width', 161), ('r_frame_rate', '240/1')]:
            info = copy.deepcopy(self.info)
            info['streams'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                inspect_source(info, {})
        self.info['streams'][1]['channels'] = 6
        with self.assertRaisesRegex(ValueError, 'mono/stereo'):
            inspect_source(self.info, {})

    def test_missing_stream_duration_is_not_guessed(self):
        del self.info['streams'][0]['duration']
        with self.assertRaisesRegex(ValueError, 'duration'):
            inspect_source(self.info, {})


if __name__ == '__main__':
    unittest.main()
