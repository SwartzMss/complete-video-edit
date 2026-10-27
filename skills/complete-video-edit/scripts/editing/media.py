"""Media probing, subprocess recording and the fixed v1 rendering profile."""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

PROFILE = {'video_codec': 'h264', 'encoder': 'libx264', 'crf': 18, 'preset': 'medium',
           'pixel_format': 'yuv420p', 'color_range': 'tv',
           'audio_codec': 'aac', 'audio_bitrate': '192k',
           'audio_sample_rate': 48000}


def write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


class Runner:
    def __init__(self, record=None, record_path=None):
        self.record = record if record is not None else {'commands': []}
        self.record_path = record_path

    def save(self):
        if self.record_path:
            write_json(self.record_path, self.record)

    def run(self, argv, timeout=None):
        entry = {'argv': [str(a) for a in argv], 'status': 'running'}
        self.record.setdefault('commands', []).append(entry)
        self.save()
        try:
            result = subprocess.run(entry['argv'], stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=timeout)
            entry.update(returncode=result.returncode, stderr=result.stderr[-16000:])
            if result.returncode:
                raise ValueError(f'{Path(argv[0]).name} exited {result.returncode}: {result.stderr[-4000:]}')
            entry['status'] = 'succeeded'
            return result.stdout
        except BaseException as exc:
            entry.update(status='failed', error=str(exc) or type(exc).__name__)
            raise
        finally:
            self.save()


def binary(name):
    found = shutil.which(str(name))
    if not found:
        raise ValueError(f'executable not found: {name}')
    return str(Path(found).resolve())


def probe(path, ffprobe, runner, count=False):
    args = [ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json']
    if count:
        args += ['-count_frames']
    return json.loads(runner.run(args + [str(path)], timeout=None if count else 120))


def _duration(stream, origin):
    if stream.get('duration_ts') is not None and stream.get('time_base'):
        return Fraction(stream['duration_ts']) * Fraction(stream['time_base'])
    value = stream.get('duration')
    if value not in (None, 'N/A'):
        return Fraction(value)
    value = stream.get('tags', {}).get('DURATION')
    if value:
        hours, minutes, seconds = value.split(':')
        # Matroska DURATION is the end timestamp, including stream offset.
        return int(hours) * 3600 + int(minutes) * 60 + Fraction(seconds) - Fraction(str(origin))
    # Do not use container duration: another stream may extend beyond the picture.
    raise ValueError('video stream has no reliable duration; remux/probe the source before planning cuts')


def inspect_source(info, plan):
    streams = info.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video']
    if len(videos) != 1 or videos[0].get('disposition', {}).get('attached_pic'):
        raise ValueError('v1 requires exactly one video stream (no attached pictures)')
    video = videos[0]
    rotation = float(video.get('tags', {}).get('rotate', 0))
    for item in video.get('side_data_list', []):
        rotation = float(item.get('rotation', rotation))
    if rotation % 360:
        raise ValueError('rotated video is not supported in v1; normalize orientation explicitly first')
    if video.get('sample_aspect_ratio', '1:1') not in ('1:1', 'N/A'):
        raise ValueError('non-square pixels are not supported in v1')
    pix_fmt = video.get('pix_fmt')
    if pix_fmt is None:
        raise ValueError('FFprobe did not report video pixel format; the selected FFprobe build may lack the source decoder; use a full FFprobe build or a supported source codec')
    if video.get('color_transfer') in ('smpte2084', 'arib-std-b67') or pix_fmt not in (
            'yuv420p', 'yuvj420p', 'yuv422p', 'yuvj422p', 'yuv444p', 'yuvj444p', 'rgb24', 'bgr24', 'gbrp'):
        raise ValueError('HDR/high-bit-depth or unsupported pixel format; explicit conversion is required')
    if video.get('field_order', 'progressive') not in ('progressive', 'unknown'):
        raise ValueError('interlaced video is not supported in v1')
    width, height = int(video['width']), int(video['height'])
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError('v1 requires positive even video dimensions')
    fps = Fraction(video.get('r_frame_rate', '0/1'))
    if fps <= 0 or fps > 120:
        raise ValueError('unsupported nominal frame rate (must be > 0 and <= 120)')
    origin = float(video.get('start_time', info.get('format', {}).get('start_time', 0)))
    duration = _duration(video, origin)
    # Matroska timestamps commonly have millisecond resolution. A rounded end
    # timestamp within one container tick of a frame boundary is that boundary,
    # not evidence for another frame. MP4 duration_ts avoids decimal rounding.
    tick = Fraction(video.get('time_base', '1/1000000000'))
    nearest_frame = round(duration * fps)
    if abs(duration - nearest_frame / fps) <= min(tick, Fraction(1, 4) / fps):
        duration = nearest_frame / fps
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(origin):
        raise ValueError('invalid source video timing')
    audios = [s for s in streams if s.get('codec_type') == 'audio']
    if 'audio_stream' in plan:
        selected = [s for s in audios if s['index'] == plan['audio_stream']]
        if not selected:
            raise ValueError('audio_stream does not select an existing audio stream')
        audio = selected[0]
    elif len(audios) > 1:
        raise ValueError('multiple audio streams: set audio_stream to an absolute stream index')
    else:
        audio = audios[0] if audios else None
    if audio and audio.get('channels') not in (1, 2):
        raise ValueError('v1 supports mono/stereo audio only')
    return {'video_stream': video['index'], 'audio_stream': audio['index'] if audio else None,
            'channels': audio['channels'] if audio else 0, 'width': width, 'height': height,
            'fps': str(fps), 'origin': origin, 'duration': float(duration), 'duration_exact': str(duration),
            'color_range': video.get('color_range', 'unknown'), 'pixel_format': pix_fmt}


def filter_graph(media, timeline):
    segments = timeline['segments']
    count = len(segments)
    origin = f'{media["origin"]:.9f}'
    rate = timeline['fps']
    color_range = media.get('color_range', 'unknown')
    pixel_format = media.get('pixel_format', '')
    input_range = 'full' if color_range == 'pc' or (
        color_range not in ('tv', 'mpeg', 'limited') and
        (pixel_format.startswith('yuvj') or pixel_format in ('rgb24', 'bgr24', 'gbrp'))
    ) else 'limited'
    # Normalize the decoded source range before encoding to the fixed yuv420p
    # limited-range output profile. Without this, full-range inputs can become
    # yuvj420p and fail the post-render profile check.
    normalize_color = f'scale=in_range={input_range}:out_range=limited,format=yuv420p'
    # Pad by one frame for ceil(duration * fps), then cap by the final frame index.
    graph = [f'[0:{media["video_stream"]}]setpts=PTS-({origin})/TB,'
             f'fps=fps={rate}:start_time=0:round=near,{normalize_color},'
             'tpad=stop_mode=clone:stop=1,'
             f'split={count}' + ''.join(f'[vin{i}]' for i in range(count))]
    has_audio = media['audio_stream'] is not None
    if has_audio:
        graph.append(f'[0:{media["audio_stream"]}]asetpts=PTS-({origin})/TB,'
                     'aresample=48000:async=1:first_pts=0,apad,'
                     f'asplit={count}' + ''.join(f'[ain{i}]' for i in range(count)))
    for i, segment in enumerate(segments):
        graph.append(f'[vin{i}]trim=start_frame={segment["source_start_frame"]}:'
                     f'end_frame={segment["source_end_frame"]},setpts=PTS-STARTPTS[v{i}]')
        if has_audio:
            start, end = segment['source_start'], segment['source_end']
            graph.append(f'[ain{i}]atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS[a{i}]')
    inputs = ''.join(f'[v{i}]' + (f'[a{i}]' if has_audio else '') for i in range(count))
    graph.append(inputs + f'concat=n={count}:v=1:a={int(has_audio)}[vout]' + ('[aout]' if has_audio else ''))
    return ';\n'.join(graph)


def cli_options(help_text):
    """Detect flags instead of guessing from vendor-specific version strings."""
    flags = set(re.findall(r'^\s*(-[a-z_]+)(?=\s|\[|:)', help_text, re.MULTILINE))
    return {'graph': '-filter_complex_script' if '-filter_complex_script' in flags else '-/filter_complex',
            'sync': '-fps_mode' if '-fps_mode' in flags else '-vsync'}


def render_command(ffmpeg, source, partial, graph_path, media, timeline, options):
    cmd = [ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-n', '-xerror', '-copyts',
           '-noautorotate', '-i', str(source), '-filter_complex_threads', '1',
           options['graph'], str(graph_path), '-map', '[vout]']
    if media['audio_stream'] is not None:
        cmd += ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000']
    cmd += ['-map_metadata', '-1', '-map_chapters', '-1', '-c:v', 'libx264', '-preset', 'medium',
            '-crf', '18', '-pix_fmt', 'yuv420p', '-r', timeline['fps'], options['sync'], 'cfr',
            '-movflags', '+faststart', str(partial)]
    return cmd
