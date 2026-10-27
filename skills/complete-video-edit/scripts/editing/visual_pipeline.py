"""Stage optional visual effects; render pictures and preserve master audio."""
from fractions import Fraction
from pathlib import Path
import shutil

from .media import Runner, binary, digest, probe, write_json
from .pipeline import verify, verify_media
from .plan import read_json, _fields
from .visual_plan import integer, resolve_plan

PROJECT = Path(__file__).resolve().parents[2] / 'remotion'


def prepare(plan_path, output, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('workspace directory already exists; choose a new version')
    plan = read_json(plan_path)
    _fields(plan, {'schema_version', 'edit_result', 'effects'}, set(), 'visual plan')
    if not isinstance(plan['edit_result'], str) or not plan['edit_result'].strip():
        raise ValueError('edit_result must be a local result directory')
    master = (plan_path.parent / plan['edit_result']).resolve()
    report = verify(master, ffmpeg, ffprobe, persist=False)
    if report['status'] != 'passed':
        raise ValueError('master verification failed: ' + '; '.join(report['errors']))
    run, mapping = read_json(master / 'run.json'), read_json(master / 'timeline.json')
    effects = resolve_plan(plan, plan_path.parent, mapping)
    output.mkdir(parents=True, exist_ok=False)
    record = {'status': 'preparing', 'schema_version': 1, 'edit_result': str(master),
              'media': run['media'], 'timeline': mapping, 'files': {}, 'source_assets': [],
              'review_status': 'pending_human_review'}
    runner = Runner(record, output / 'workspace.json')
    try:
        ffmpeg, ffprobe = binary(ffmpeg), binary(ffprobe)
        public = output / 'public'
        public.mkdir()
        write_json(output / 'visual-plan.json', plan)
        shutil.copyfile(master / 'output.mp4', public / 'master.mp4')
        if digest(public / 'master.mp4') != run['output_sha256']:
            raise ValueError('master changed while staging')
        record['files']['public/master.mp4'] = run['output_sha256']
        for index, effect in enumerate(effects):
            staged = []
            for photo_index, source in enumerate(effect['photos']):
                source = Path(source)
                fingerprint = digest(source)
                name = f'photo-{index}-{photo_index}{source.suffix.lower()}'
                shutil.copyfile(source, public / name)
                if digest(public / name) != fingerprint:
                    raise ValueError('photo changed while staging')
                info = probe(public / name, ffprobe, runner, count=True)
                streams = info.get('streams', [])
                if (len(streams) != 1 or streams[0].get('codec_name') not in ('png', 'mjpeg', 'webp')
                        or int(streams[0].get('nb_read_frames', 0)) != 1):
                    raise ValueError(f'photo must be a decodable single-frame PNG/JPEG/WebP: {source}')
                runner.run([ffmpeg, '-v', 'error', '-nostdin', '-xerror', '-i', str(public / name),
                            '-map', '0:v:0', '-frames:v', '1', '-f', 'null', '-'])
                record['source_assets'].append({'source': str(source), 'staged': name, 'sha256': fingerprint})
                record['files']['public/' + name] = fingerprint
                staged.append(name)
            effect['photos'] = staged
        props = {'video': 'master.mp4', 'width': run['media']['width'], 'height': run['media']['height'],
                 'fps': float(Fraction(mapping['fps'])), 'durationInFrames': mapping['expected_frames'],
                 'effects': effects, 'muted': False}
        write_json(output / 'props.json', props)
        for name in ('props.json', 'visual-plan.json'):
            record['files'][name] = digest(output / name)
        record['status'] = 'prepared'
        return {'status': 'prepared', 'workspace': str(output), 'props': str(output / 'props.json')}
    except BaseException as exc:
        record.update(status='failed', error=str(exc) or type(exc).__name__)
        raise
    finally:
        write_json(output / 'workspace.json', record)


def workspace_record(workspace):
    record = read_json(workspace / 'workspace.json')
    if not isinstance(record, dict) or record.get('status') != 'prepared':
        raise ValueError('workspace did not prepare successfully')
    files = record.get('files')
    if not isinstance(files, dict) or not {'props.json', 'visual-plan.json', 'public/master.mp4'} <= files.keys():
        raise ValueError('invalid workspace file manifest')
    for name, expected in files.items():
        path = (workspace / name).resolve()
        if not path.is_relative_to(workspace) or digest(path) != expected:
            raise ValueError(f'staged input changed: {name}; change the plan and prepare a new workspace')
    return record


def audio_hash(path, ffmpeg, runner):
    return runner.run([ffmpeg, '-v', 'error', '-nostdin', '-i', str(path), '-map', '0:a:0',
                       '-c:a', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).strip()


def render(workspace, output, ffmpeg='ffmpeg', ffprobe='ffprobe', node='node',
           start_frame=0, end_frame=None, stills=False):
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('result directory already exists; choose a new version')
    prepared = workspace_record(workspace)
    total = prepared['timeline']['expected_frames']
    start = integer(start_frame, 'start_frame')
    end = total if end_frame is None else integer(end_frame, 'end_frame', 1)
    if not start < end <= total:
        raise ValueError('preview range must satisfy 0 <= start < end <= total frames')
    full = start == 0 and end == total
    has_audio = prepared['media']['audio_stream'] is not None
    output.mkdir(parents=True, exist_ok=False)
    record = {'status': 'running', 'engine': 'Remotion + FFmpeg audio mux', 'workspace': str(workspace),
              'frame_range': [start, end], 'kind': 'full' if full else 'preview',
              'audio_mode': ('copied_master_aac' if full else 'trimmed_preview_aac') if has_audio else 'none',
              'review_status': 'pending_human_review', 'commands': []}
    runner = Runner(record, output / 'run.json')
    partial, silent = output / 'output.partial.mp4', output / 'picture.partial.mp4'
    try:
        runner.save()
        ffmpeg, ffprobe, node = binary(ffmpeg), binary(ffprobe), binary(node)
        if not (PROJECT / 'node_modules/@remotion/renderer').is_dir():
            raise ValueError(f'Remotion dependencies missing: run npm ci in {PROJECT}; Skills alone are not a runtime')
        record['versions'] = {name: runner.run([exe, flag], timeout=30).splitlines()[0]
                              for name, exe, flag in [('node', node, '--version'), ('ffmpeg', ffmpeg, '-version')]}
        write_json(output / 'props.json', read_json(workspace / 'props.json'))
        write_json(output / 'workspace-snapshot.json', prepared)
        cmd = [node, str(PROJECT / 'scripts/run.mjs'), 'render', str(workspace), str(silent), str(start), str(end)]
        if stills:
            cmd.append('--stills')
        runner.run(cmd)
        master = workspace / 'public/master.mp4'
        mux = [ffmpeg, '-v', 'error', '-nostdin', '-n', '-xerror', '-i', str(silent)]
        if has_audio:
            mux += ['-i', str(master), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy']
            if full:
                mux += ['-c:a', 'copy']
            else:
                rate = Fraction(prepared['timeline']['fps'])
                mux += ['-af', f'atrim=start={float(start / rate):.9f}:end={float(end / rate):.9f},asetpts=PTS-STARTPTS',
                        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000']
        else:
            mux += ['-map', '0:v:0', '-c:v', 'copy', '-an']
        mux += ['-map_metadata', '-1', '-movflags', '+faststart', str(partial)]
        runner.run(mux)
        mapping = {**prepared['timeline'], 'expected_frames': end - start,
                   'expected_duration': float((end - start) / Fraction(prepared['timeline']['fps']))}
        report = verify_media(partial, prepared['media'], mapping, ffmpeg, ffprobe, runner)
        if full and has_audio:
            hashes = {'master': audio_hash(master, ffmpeg, runner), 'output': audio_hash(partial, ffmpeg, runner)}
            report['audio_payload_hashes'] = hashes
            report['checks']['original_audio_payload'] = hashes['master'] == hashes['output']
            if not report['checks']['original_audio_payload']:
                report['status'] = 'failed'
                report['errors'].append('original audio payload changed')
        write_json(output / 'verification.json', report)
        if report['status'] != 'passed':
            actual = report.get('actual', {})
            streams = [{k: stream.get(k) for k in ('codec_type', 'codec_name', 'pix_fmt', 'color_range',
                                                   'avg_frame_rate', 'r_frame_rate', 'time_base')}
                       for stream in actual.get('streams', [])]
            raise ValueError('; '.join(report['errors']) +
                             f'; expected fps={mapping["fps"]}, actual fps={actual.get("fps")}, streams={streams}')
        workspace_record(workspace)  # Detect input edits during rendering.
        record.update(status='verified', output_sha256=report['output_sha256'], output='output.mp4')
        runner.save()
        if (output / 'output.mp4').exists():
            raise ValueError('refusing to overwrite output.mp4')
        partial.rename(output / 'output.mp4')
        return {'status': 'verified', 'output': str(output / 'output.mp4'), 'kind': record['kind'],
                'review_status': 'pending_human_review'}
    except BaseException as exc:
        record.update(status='failed', error=str(exc) or type(exc).__name__)
        runner.save()
        raise
    finally:
        for path in (partial, silent):
            if path.exists():
                path.unlink()
