"""Versioned asset manifests and read-only diagnostics (Python standard library only)."""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

KINDS = {'video', 'audio', 'image', 'template'}
TOOLS = {'ffmpeg', 'ffprobe', 'node'}


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError('invalid fields; required: ' + ', '.join(sorted(required)))


def string(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('expected a non-empty string')


def strings(value):
    if not isinstance(value, list):
        raise ValueError('expected a string list')
    for item in value:
        string(item)


def choice(value, choices):
    if not isinstance(value, str) or value not in choices:
        raise ValueError('expected one of: ' + ', '.join(sorted(choices)))


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9]+(?:[-_][a-z0-9]+)*', value):
        raise ValueError('IDs must use lowercase letters, digits, hyphens or underscores')


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f'duplicate JSON key: {key}')
        obj[key] = value
    return obj


def local_path(directory, value):
    string(value)
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('', '.', '..') for part in value.split('/')) or re.search(r'[:\\\x00-\x1f]', value):
        raise ValueError('file path must be a portable relative path inside its manifest directory')
    resolved = (directory / value).resolve()
    if not resolved.is_relative_to(directory.resolve()):
        raise ValueError('file path escapes manifest directory through a symlink')
    return resolved


def validate_metadata(data):
    fields(data, (), ('duration_seconds', 'width', 'height', 'fps', 'video_codec', 'audio_codec',
                      'has_alpha', 'has_audio', 'sample_rate', 'channels', 'peak_dbfs'))
    for key, value in data.items():
        if key in ('has_alpha', 'has_audio'):
            if type(value) is not bool:
                raise ValueError(f'{key} must be boolean')
        elif key in ('width', 'height', 'sample_rate', 'channels'):
            if type(value) is not int or value <= 0:
                raise ValueError(f'{key} must be a positive integer')
        elif key in ('duration_seconds', 'peak_dbfs'):
            if type(value) not in (int, float) or not math.isfinite(value) or (key == 'duration_seconds' and value <= 0):
                raise ValueError(f'invalid {key}')
        elif key == 'fps':
            string(value)
            if Fraction(value) <= 0:
                raise ValueError('fps must be positive')
        else:
            string(value)


def load_manifest(path):
    data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_pairs)
    fields(data, ('schema_version', 'asset_id', 'name', 'kind', 'description', 'usage', 'files'))
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported schema_version; expected 1')
    identifier(data['asset_id'])
    for key in ('name', 'description'):
        string(data[key])
    choice(data['kind'], KINDS | {'bundle'})
    strings(data['usage'])
    if not data['usage'] or not isinstance(data['files'], list) or not data['files']:
        raise ValueError('usage and files must not be empty')
    ids, paths = set(), set()
    for item in data['files']:
        fields(item, ('file_id', 'path', 'kind', 'role', 'storage', 'source', 'rights', 'requires'),
               ('sha256', 'metadata', 'notes'))
        identifier(item['file_id'])
        resolved = local_path(path.parent, item['path'])
        if item['file_id'] in ids or resolved in paths:
            raise ValueError('duplicate file ID or path')
        ids.add(item['file_id'])
        paths.add(resolved)
        choice(item['kind'], KINDS)
        string(item['role'])
        choice(item['storage'], {'bundled', 'local_only'})
        strings(item['requires'])
        if set(item['requires']) - TOOLS:
            raise ValueError('requires supports only ffmpeg, ffprobe, node executable checks')
        if 'sha256' in item and (not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256'])):
            raise ValueError('sha256 must contain 64 lowercase hexadecimal characters')
        source = item['source']
        fields(source, ('url', 'description'), ('interval_seconds', 'crop'))
        string(source['description'])
        if source['url'] is not None and (not isinstance(source['url'], str) or not re.match(r'https?://[^/\s]+', source['url'])):
            raise ValueError('source.url must be an HTTP(S) URL or null')
        if 'interval_seconds' in source:
            interval = source['interval_seconds']
            if (not isinstance(interval, list) or len(interval) != 2 or
                    any(type(v) not in (int, float) or not math.isfinite(v) for v in interval) or
                    not 0 <= interval[0] < interval[1]):
                raise ValueError('source.interval_seconds must be [start, end] with 0 <= start < end')
        if 'crop' in source:
            string(source['crop'])
        rights = item['rights']
        fields(rights, ('license', 'redistribution', 'notes'))
        string(rights['license'])
        string(rights['notes'])
        choice(rights['redistribution'], {'allowed', 'prohibited', 'unknown'})
        if 'metadata' in item:
            validate_metadata(item['metadata'])
        if 'notes' in item:
            strings(item['notes'])
    return data


def issue(target, code, severity, message):
    target['issues'].append({'code': code, 'severity': severity, 'message': message})


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(args):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=30)
    if result.returncode:
        raise ValueError(result.stderr[-2000:] or f'exit code {result.returncode}')
    return result.stdout


def check_file(item, directory, tools, decode):
    result = {**item, 'existence': 'not_checked', 'hash': {'status': 'not_checked'},
              'probe': {'status': 'not_checked'}, 'decode': {'status': 'not_checked'},
              'browser_preview': 'not_checked', 'render': 'not_checked', 'issues': [],
              'dependencies': {name: 'found' if tools[name] else 'missing' for name in item['requires']}}
    for name, status in result['dependencies'].items():
        if status == 'missing':
            issue(result, 'dependency_missing', 'warning', f'{name} executable not found; capabilities are unverified')
    if item['rights']['redistribution'] != 'allowed':
        issue(result, 'redistribution_' + item['rights']['redistribution'], 'warning',
              'Redistribution declaration: ' + item['rights']['redistribution'] + '; ' + item['rights']['notes'])
    try:
        path = local_path(directory, item['path'])
        if not path.exists():
            result['existence'] = 'missing'
            local = item['storage'] == 'local_only'
            issue(result, 'local_file_missing' if local else 'bundled_file_missing', 'warning' if local else 'error',
                  'File missing; no download attempted. Source: ' + (item['source']['url'] or item['source']['description']))
            return result
        if not path.is_file():
            raise OSError('asset path is not a regular file')
        # Opening the file distinguishes presence from readability, even without a hash.
        with path.open('rb') as stream:
            stream.read(1)
        result['existence'] = 'present'
        if 'sha256' in item:
            actual = digest(path)
            result['hash'] = {'status': 'matched' if actual == item['sha256'] else 'mismatch', 'actual': actual}
            if actual != item['sha256']:
                issue(result, 'hash_mismatch', 'error', 'SHA-256 differs from the registered file; media checks skipped')
                return result
        else:
            result['hash']['status'] = 'not_configured'
    except (OSError, ValueError) as exc:
        result['existence'] = 'unreadable'
        issue(result, 'file_unreadable', 'error', str(exc))
        return result
    if item['kind'] == 'template':
        result['probe']['status'] = result['decode']['status'] = 'not_applicable'
        return result
    if not tools['ffprobe']:
        result['probe']['status'] = 'tool_missing'
        issue(result, 'probe_tool_missing', 'warning', 'FFprobe unavailable; media properties were not checked')
    else:
        try:
            info = json.loads(run([tools['ffprobe'], '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_streams', '-show_format', '-of', 'json', str(path)]))
            if not isinstance(info, dict):
                raise ValueError('FFprobe returned a non-object response')
            streams = info.get('streams', [])
            if not isinstance(streams, list) or any(not isinstance(s, dict) for s in streams):
                raise ValueError('FFprobe returned invalid stream information')
            expected_type = 'audio' if item['kind'] == 'audio' else 'video'
            if not any(s.get('codec_type') == expected_type for s in streams):
                raise ValueError('no stream matching the declared media kind')
            result['probe'] = {'status': 'passed', 'streams': streams, 'format': info.get('format', {})}
        except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired) as exc:
            result['probe']['status'] = 'failed'
            issue(result, 'probe_failed', 'error', str(exc))
    if decode:
        if not tools['ffmpeg']:
            result['decode']['status'] = 'tool_missing'
            issue(result, 'decode_tool_missing', 'warning', 'FFmpeg unavailable; sample decoding was not checked')
        else:
            try:
                # No output file, no stdin, no manifest-provided commands. This only samples the start.
                run([tools['ffmpeg'], '-v', 'error', '-nostdin', '-xerror', '-protocol_whitelist', 'file,pipe', '-i', str(path), '-t', '1',
                     '-map', '0:v?', '-map', '0:a?', '-f', 'null', '-'])
                result['decode'] = {'status': 'sample_passed', 'scope': 'first_second_only', 'tool': 'ffmpeg'}
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                result['decode'] = {'status': 'failed', 'scope': 'first_second_only', 'tool': 'ffmpeg'}
                issue(result, 'decode_failed', 'error', str(exc))
    return result


def inventory(root, ffprobe='ffprobe', ffmpeg='ffmpeg', decode=False):
    root = Path(root).resolve()
    tools = {name: shutil.which(executable) for name, executable in
             [('ffprobe', ffprobe), ('ffmpeg', ffmpeg), ('node', 'node')]}
    report = {'schema_version': 1, 'root': str(root), 'tools': tools, 'assets': [], 'issues': []}
    seen = set()
    try:
        if not root.is_dir():
            raise ValueError('asset root is not a directory')
        manifests = sorted(root.rglob('manifest.json'))
        if not manifests:
            raise ValueError('no manifest.json files found under asset root')
        for path in manifests:
            asset = {'manifest': path.relative_to(root).as_posix(), 'manifest_status': 'invalid', 'files': [], 'issues': []}
            report['assets'].append(asset)
            try:
                if not path.resolve().is_relative_to(root):
                    raise ValueError('manifest symlink escapes asset root')
                data = load_manifest(path)
                if data['asset_id'] in seen:
                    raise ValueError('duplicate asset_id: ' + data['asset_id'])
                seen.add(data['asset_id'])
                asset.update({k: v for k, v in data.items() if k != 'files'})
                asset['manifest_status'] = 'valid'
                asset['files'] = [check_file(item, path.parent, tools, decode) for item in data['files']]
            except (OSError, ValueError, ZeroDivisionError, OverflowError, RuntimeError) as exc:
                issue(asset, 'manifest_invalid', 'error', str(exc))
    except (OSError, ValueError) as exc:
        issue(report, 'inventory_failed', 'error', str(exc))
    issues = report['issues'] + [i for a in report['assets'] for i in a['issues']] + [
        i for a in report['assets'] for f in a['files'] for i in f['issues']]
    report['summary'] = {'assets': len(report['assets']),
                         'errors': sum(i['severity'] == 'error' for i in issues),
                         'warnings': sum(i['severity'] == 'warning' for i in issues)}
    return report


def text_report(report):
    lines = ['Asset inventory: ' + report['root']]
    for asset in report['assets']:
        lines.append(f"{asset.get('asset_id', asset['manifest'])}: manifest={asset['manifest_status']}")
        for item in asset['files']:
            lines.append(f"  {item['path']} [{item['storage']}]: file={item['existence']}, hash={item['hash']['status']}, "
                         f"probe={item['probe']['status']}, decode={item['decode']['status']}, "
                         f"redistribution={item['rights']['redistribution']}")
            for entry in item['issues']:
                lines.append(f"    {entry['severity']} {entry['code']}: {entry['message']}")
        for entry in asset['issues']:
            lines.append(f"  {entry['severity']} {entry['code']}: {entry['message']}")
    for entry in report['issues']:
        lines.append(f"{entry['severity']} {entry['code']}: {entry['message']}")
    lines.append(f"{report['summary']['errors']} errors, {report['summary']['warnings']} warnings. "
                 'Browser preview and final rendering are not checked; decode is only a one-second sample.')
    return '\n'.join(lines)
