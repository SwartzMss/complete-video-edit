"""Strict decision validation and derived, frame-aligned time mapping."""
from fractions import Fraction
import json
import math
from pathlib import Path
import re


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=_object)


def _fields(data, required, optional, name):
    if not isinstance(data, dict):
        raise ValueError(f'{name} must be an object')
    missing = required - data.keys()
    unknown = data.keys() - required - optional
    if missing or unknown:
        raise ValueError(f'{name}: missing fields {sorted(missing)}, unsupported fields {sorted(unknown)}')


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number of seconds')
    return Fraction(str(value))


def validate_plan(data, duration=None):
    _fields(data, {'schema_version', 'source', 'cuts'}, {'source_sha256', 'audio_stream'}, 'plan')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported schema_version (expected integer 1)')
    if not isinstance(data['source'], str) or not data['source'].strip():
        raise ValueError('source must be a nonempty local file path')
    if 'source_sha256' in data and (not isinstance(data['source_sha256'], str) or
                                   not re.fullmatch('[0-9a-f]{64}', data['source_sha256'])):
        raise ValueError('source_sha256 must be 64 lowercase hexadecimal characters')
    if 'audio_stream' in data and (type(data['audio_stream']) is not int or data['audio_stream'] < 0):
        raise ValueError('audio_stream must be a nonnegative absolute stream index')
    if not isinstance(data['cuts'], list):
        raise ValueError('cuts must be an array')
    if len(data['cuts']) > 128:
        raise ValueError('v1 supports at most 128 cuts per plan')
    previous_end = Fraction(0)
    ids = set()
    for index, cut in enumerate(data['cuts']):
        name = f'cuts[{index}]'
        _fields(cut, {'id', 'start', 'end', 'reason'}, set(), name)
        for field in ('id', 'reason'):
            if not isinstance(cut[field], str) or not cut[field].strip():
                raise ValueError(f'{name}.{field} must be a nonblank string')
        if cut['id'] in ids:
            raise ValueError(f'{name}: duplicate id {cut["id"]}')
        ids.add(cut['id'])
        start, end = (_number(cut[k], f'{name}.{k}') for k in ('start', 'end'))
        if start < previous_end or end <= start:
            raise ValueError(f'{name}: cuts must be positive, sorted, nonnegative and nonoverlapping')
        if duration is not None and end > Fraction(str(duration)):
            raise ValueError(f'{name}: end exceeds source duration {duration}')
        previous_end = end


def load_plan(path):
    path = Path(path).resolve()
    data = read_json(path)
    validate_plan(data)
    source = (path.parent / data['source']).resolve()
    if not source.is_file():
        raise ValueError(f'source file does not exist: {source}')
    return data, source


def timeline(data, duration, fps):
    validate_plan(data, duration)
    rate = Fraction(fps)
    if rate <= 0 or rate > 120:
        raise ValueError('frame rate must be positive and at most 120 fps')
    total_frames = math.ceil(Fraction(str(duration)) * rate)
    if total_frames <= 0:
        raise ValueError('source duration must be positive')
    cursor = output_frame = 0
    segments, cuts = [], []

    def keep(start, end):
        nonlocal output_frame
        if end <= start:
            return
        count = end - start
        segments.append({'id': f'keep-{len(segments) + 1:03d}',
                         'source_start_frame': start, 'source_end_frame': end,
                         'source_start': float(start / rate), 'source_end': float(end / rate),
                         'output_start_frame': output_frame, 'output_end_frame': output_frame + count,
                         'output_start': float(output_frame / rate),
                         'output_end': float((output_frame + count) / rate), 'speed': 1.0})
        output_frame += count

    for cut in data['cuts']:
        start = math.ceil(Fraction(str(cut['start'])) * rate)
        end = math.ceil(Fraction(str(cut['end'])) * rate)
        if end <= start:
            raise ValueError(f'cut {cut["id"]} contains no frame after quantization')
        keep(cursor, start)
        cuts.append({**cut, 'effective_start': float(start / rate), 'effective_end': float(end / rate)})
        cursor = end
    keep(cursor, total_frames)
    if not segments:
        raise ValueError('plan removes all video frames')
    return {'schema_version': 1, 'fps': str(rate), 'source_duration': float(duration),
            'expected_frames': output_frame, 'expected_duration': float(output_frame / rate),
            'segments': segments, 'cuts': cuts}
