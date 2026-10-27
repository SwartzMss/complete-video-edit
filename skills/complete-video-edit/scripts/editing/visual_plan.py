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


def single_props(effect, duration, fps, name):
    layout, motion = effect.get('layout', 'center'), effect.get('motion', 'none')
    if layout not in ('center', 'pip') or motion not in ('none', 'ken-burns'):
        raise ValueError(f'{name}: unsupported layout or motion')
    default = max(1, min(round(float(Fraction(fps)) * .5), (duration - 1) // 2))
    entry = integer(effect.get('entry_frames', default), 'entry_frames', 1)
    exit_frames = integer(effect.get('exit_frames', default), 'exit_frames', 1)
    if duration < entry + exit_frames + 1:
        raise ValueError(f'{name}: duration needs entry, exit and at least one visible hold frame')
    size = scale(effect.get('scale', .3 if layout == 'pip' else .88), 'scale', .1, .45 if layout == 'pip' else .95)
    position, margin = effect.get('position', 'bottom-right'), effect.get('margin', .04)
    if layout == 'center' and ('position' in effect or 'margin' in effect):
        raise ValueError(f'{name}: position and margin require pip layout')
    if position not in ('top-left', 'top-right', 'bottom-left', 'bottom-right'):
        raise ValueError(f'{name}: unsupported pip position')
    margin = scale(margin, 'margin', 0, .2)
    if layout == 'pip' and size + 2 * margin > 1:
        raise ValueError(f'{name}: pip box and margins must fit the canvas')
    zoom = 1
    if motion == 'ken-burns':
        zoom = scale(effect.get('zoom_factor', 1.08), 'zoom_factor', 1, 1.2)
        if zoom == 1:
            raise ValueError(f'{name}: ken-burns zoom_factor must be greater than 1')
    elif 'zoom_factor' in effect:
        raise ValueError(f'{name}: zoom_factor requires ken-burns motion')
    return {'type': 'photo-single', 'layout': layout, 'motion': motion, 'scale': size,
            'position': position, 'margin': margin, 'zoomFactor': zoom,
            'entryFrames': entry, 'exitFrames': exit_frames,
            'reviewFrames': sorted({0, entry, duration // 2, duration - exit_frames - 1, duration - 1, duration})}


def resolve_plan(data, directory, timeline):
    _fields(data, {'schema_version', 'edit_result', 'effects'}, set(), 'visual plan')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported visual schema_version')
    if not isinstance(data['edit_result'], str) or not data['edit_result'].strip():
        raise ValueError('edit_result must be a local result directory')
    if not isinstance(data['effects'], list) or not 1 <= len(data['effects']) <= 32:
        raise ValueError('effects must contain 1 to 32 photo effects; use the master directly for no effects')
    resolved, ids = [], set()
    for index, effect in enumerate(data['effects']):
        name = f'effects[{index}]'
        kind = effect.get('type') if isinstance(effect, dict) else None
        if kind not in ('photo-pair', 'photo-single'):
            raise ValueError(f'{name}: unsupported effect type')
        optional = ({'transition_frames', 'overview_scale', 'focus_scale', 'layer'} if kind == 'photo-pair' else
                    {'layout', 'motion', 'entry_frames', 'exit_frames', 'scale', 'position', 'margin', 'zoom_factor', 'layer'})
        _fields(effect, {'id', 'type', 'photos', 'timebase', 'start_frame', 'duration_frames'},
                optional, name)
        if not isinstance(effect['id'], str) or not effect['id'].strip() or effect['id'] in ids:
            raise ValueError(f'{name}: id must be nonempty and unique')
        ids.add(effect['id'])
        start = integer(effect['start_frame'], f'{name}.start_frame')
        duration = integer(effect['duration_frames'], f'{name}.duration_frames', 7 if kind == 'photo-pair' else 3)
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
        photos = effect['photos']
        count = 2 if kind == 'photo-pair' else 1
        if not isinstance(photos, list) or len(photos) != count:
            raise ValueError(f'{name}.photos must contain exactly {count} local image paths')
        paths = []
        for photo in photos:
            if not isinstance(photo, str) or not photo.strip():
                raise ValueError(f'{name}: invalid photo path')
            path = (Path(directory) / photo).resolve()
            if not path.is_file() or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError(f'{name}: missing photo or unsupported image format: {photo}')
            paths.append(str(path))
        common = {'id': effect['id'], 'startFrame': start, 'durationInFrames': duration,
                  'photos': paths, 'layer': integer(effect.get('layer', 1), 'layer', 1)}
        if kind == 'photo-single':
            resolved.append({**common, **single_props(effect, duration, timeline['fps'], name)})
        else:
            transition = integer(effect.get('transition_frames', max(1, min(round(float(Fraction(timeline['fps'])) * .7),
                                                                             (duration - 3) // 4))),
                                 f'{name}.transition_frames', 1)
            if duration - 4 * transition < 3:
                raise ValueError(f'{name}: duration needs four transitions and three nonempty holds')
            hold, remainder = divmod(duration - 4 * transition, 3)
            resolved.append({**common, 'phaseFrames': [transition, hold, transition, hold,
                                                      transition, hold + remainder, transition],
                             'overviewScale': scale(effect.get('overview_scale', .36), 'overview_scale', .1, .42),
                             'focusScale': scale(effect.get('focus_scale', .88), 'focus_scale', .5, .95)})
    ordered = sorted(resolved, key=lambda e: e['startFrame'])
    if any(a['startFrame'] + a['durationInFrames'] > b['startFrame'] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('photo effects overlap; choose disjoint windows')
    return resolved
