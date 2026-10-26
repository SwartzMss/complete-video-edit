"""Resolve optional photo effects against the authoritative edit timeline."""
from fractions import Fraction
import math
from pathlib import Path

from .plan import _fields


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def scale(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return value


def resolve_plan(data, directory, timeline):
    _fields(data, {'schema_version', 'edit_result', 'effects'}, set(), 'visual plan')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported visual schema_version')
    if not isinstance(data['edit_result'], str) or not data['edit_result'].strip():
        raise ValueError('edit_result must be a local result directory')
    if not isinstance(data['effects'], list) or not 1 <= len(data['effects']) <= 32:
        raise ValueError('effects must contain 1 to 32 photo pairs; use the master directly for no effects')
    resolved, ids = [], set()
    for index, effect in enumerate(data['effects']):
        name = f'effects[{index}]'
        _fields(effect, {'id', 'type', 'photos', 'timebase', 'start_frame', 'duration_frames'},
                {'transition_frames', 'overview_scale', 'focus_scale', 'layer'}, name)
        if not isinstance(effect['id'], str) or not effect['id'].strip() or effect['id'] in ids:
            raise ValueError(f'{name}: id must be nonempty and unique')
        ids.add(effect['id'])
        if effect['type'] != 'photo-pair':
            raise ValueError(f'{name}: only photo-pair is supported')
        start = integer(effect['start_frame'], f'{name}.start_frame')
        duration = integer(effect['duration_frames'], f'{name}.duration_frames', 7)
        if effect['timebase'] == 'source':
            matches = [s for s in timeline['segments'] if s['source_start_frame'] <= start and
                       start + duration <= s['source_end_frame']]
            if len(matches) != 1:
                raise ValueError(f'{name}: source interval must fit one retained segment; deleted/cross-cut anchor')
            start = matches[0]['output_start_frame'] + start - matches[0]['source_start_frame']
        elif effect['timebase'] != 'output':
            raise ValueError(f'{name}.timebase must be source or output')
        if start + duration > timeline['expected_frames']:
            raise ValueError(f'{name}: effect extends past the master')
        transition = integer(effect.get('transition_frames', max(1, min(round(float(Fraction(timeline['fps'])) * .7),
                                                                         (duration - 3) // 4))),
                             f'{name}.transition_frames', 1)
        if duration - 4 * transition < 3:
            raise ValueError(f'{name}: duration needs four transitions and three nonempty holds')
        hold, remainder = divmod(duration - 4 * transition, 3)
        photos = effect['photos']
        if not isinstance(photos, list) or len(photos) != 2:
            raise ValueError(f'{name}.photos must contain exactly two local image paths')
        paths = []
        for photo in photos:
            if not isinstance(photo, str) or not photo.strip():
                raise ValueError(f'{name}: invalid photo path')
            path = (Path(directory) / photo).resolve()
            if not path.is_file() or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError(f'{name}: missing photo or unsupported image format: {photo}')
            paths.append(str(path))
        resolved.append({'id': effect['id'], 'startFrame': start, 'durationInFrames': duration,
                         'photos': paths, 'phaseFrames': [transition, hold, transition, hold,
                                                        transition, hold + remainder, transition],
                         'overviewScale': scale(effect.get('overview_scale', .36), 'overview_scale', .1, .42),
                         'focusScale': scale(effect.get('focus_scale', .88), 'focus_scale', .5, .95),
                         'layer': integer(effect.get('layer', 1), 'layer', 1)})
    ordered = sorted(resolved, key=lambda e: e['startFrame'])
    if any(a['startFrame'] + a['durationInFrames'] > b['startFrame'] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('photo effects overlap; choose disjoint windows')
    return resolved
