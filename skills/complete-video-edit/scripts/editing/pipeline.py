"""Check, render and re-verify an exclusively created result bundle."""
from fractions import Fraction
from pathlib import Path

from .media import (PROFILE, Runner, binary, digest, filter_graph, inspect_source,
                    probe, render_command, write_json)
from .plan import load_plan, read_json, timeline


def prepare(plan_path, ffprobe, runner):
    data, source = load_plan(plan_path)
    source_hash = digest(source)
    if data.get('source_sha256', source_hash) != source_hash:
        raise ValueError('source_sha256 mismatch: source changed since the plan was reviewed')
    info = probe(source, ffprobe, runner)
    media = inspect_source(info, data)
    mapping = timeline(data, Fraction(media['duration_exact']), media['fps'])
    return data, source, source_hash, media, mapping


def check(plan_path, ffprobe='ffprobe'):
    runner = Runner()
    _, source, source_hash, media, mapping = prepare(plan_path, binary(ffprobe), runner)
    return {'status': 'valid', 'source': str(source), 'source_sha256': source_hash,
            'media': media, 'profile': PROFILE, 'timeline': mapping,
            'review_status': 'pending_human_review'}


def verify_media(path, media, mapping, ffmpeg, ffprobe, runner, expected_hash=None):
    report = {'status': 'failed', 'review_status': 'pending_human_review', 'checks': {}, 'errors': []}
    try:
        actual_hash = digest(path)
        report['output_sha256'] = actual_hash
        report['checks']['fingerprint'] = expected_hash is None or actual_hash == expected_hash
        info = probe(path, ffprobe, runner, count=True)
        videos = [s for s in info['streams'] if s.get('codec_type') == 'video']
        audios = [s for s in info['streams'] if s.get('codec_type') == 'audio']
        if len(videos) != 1:
            raise ValueError('expected exactly one output video stream')
        video = videos[0]
        duration = float(info['format']['duration'])
        fps = Fraction(video['avg_frame_rate'])
        frames = int(video['nb_read_frames'])
        tolerance = max(0.05, 1 / float(Fraction(mapping['fps'])) + 1024 / 48000)
        expected_audio = media['audio_stream'] is not None
        report['actual'] = {'duration': duration, 'width': video['width'], 'height': video['height'],
                            'fps': str(fps), 'frames': frames, 'has_audio': bool(audios),
                            'streams': info['streams']}
        report.update(expected_duration=mapping['expected_duration'], duration_tolerance=tolerance)
        report['checks'].update(
            dimensions=(video['width'], video['height']) == (media['width'], media['height']),
            frame_rate=fps == Fraction(mapping['fps']),
            frame_count=frames == mapping['expected_frames'],
            duration=abs(duration - mapping['expected_duration']) <= tolerance,
            video_duration=abs(float(video['duration']) - mapping['expected_duration']) <= tolerance,
            video_profile=video.get('codec_name') == 'h264' and video.get('pix_fmt') == 'yuv420p',
            audio_streams=len(audios) == int(expected_audio),
            video_start=abs(float(video.get('start_time', 0))) <= 1 / float(fps))
        if expected_audio and len(audios) == 1:
            audio = audios[0]
            report['checks'].update(
                audio_profile=(audio.get('codec_name') == 'aac' and int(audio['sample_rate']) == 48000
                               and audio.get('channels') == media['channels']),
                audio_start=abs(float(audio.get('start_time', 0))) <= 1024 / 48000,
                audio_duration=abs(float(audio['duration']) - mapping['expected_duration']) <= tolerance)
        runner.run([ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-xerror', '-i', str(path),
                    '-map', '0:v', '-map', '0:a?', '-f', 'null', '-'])
        report['checks']['complete_decode'] = True
        report['errors'] += [f'check failed: {key}' for key, passed in report['checks'].items() if not passed]
        if not report['errors']:
            report['status'] = 'passed'
    except (OSError, ValueError, KeyError, ZeroDivisionError) as exc:
        report['errors'].append(str(exc))
    return report


def render(plan_path, output, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f'output directory already exists: {output}')
    # Reject invalid plans before creating any output directory.
    preflight = Runner()
    ffprobe = binary(ffprobe)
    data, source, source_hash, media, mapping = prepare(plan_path, ffprobe, preflight)
    output.mkdir(parents=True, exist_ok=False)
    record = {'status': 'running', 'source': str(source), 'source_sha256': source_hash,
              'profile': PROFILE, 'media': media, 'commands': preflight.record['commands'],
              'output': 'output.mp4', 'review_status': 'pending_human_review'}
    runner = Runner(record, output / 'run.json')
    partial = output / 'output.partial.mp4'
    try:
        runner.save()
        write_json(output / 'plan.json', data)
        write_json(output / 'timeline.json', mapping)
        graph_path = output / 'filter.ffscript'
        graph_path.write_text(filter_graph(media, mapping), encoding='utf-8')
        record['artifact_sha256'] = {name: digest(output / name)
                                     for name in ('plan.json', 'timeline.json', 'filter.ffscript')}
        ffmpeg = binary(ffmpeg)
        record['versions'] = {name: runner.run([exe, '-version'], timeout=30).splitlines()[0]
                              for name, exe in [('ffmpeg', ffmpeg), ('ffprobe', ffprobe)]}
        runner.run(render_command(ffmpeg, source, partial, graph_path, media, mapping))
        if digest(source) != source_hash:
            raise ValueError('source changed during rendering')
        report = verify_media(partial, media, mapping, ffmpeg, ffprobe, runner)
        write_json(output / 'verification.json', report)
        if report['status'] != 'passed':
            raise ValueError('; '.join(report['errors']))
        record.update(status='verified', output_sha256=report['output_sha256'])
        runner.save()
        # Exclusive directory plus non-overwriting publication protects original media.
        destination = output / 'output.mp4'
        if destination.exists():
            raise ValueError('output.mp4 unexpectedly exists; refusing to overwrite')
        partial.rename(destination)
        return {'status': 'verified', 'output': str(destination), 'result_directory': str(output),
                'expected_duration': mapping['expected_duration'], 'review_status': 'pending_human_review'}
    except BaseException as exc:
        record.update(status='failed', error=str(exc) or type(exc).__name__)
        runner.save()
        if partial.exists():
            partial.unlink()
        raise


def verify(output, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    output = Path(output).resolve()
    runner = Runner()
    try:
        # Do not follow paths supplied by run.json to arbitrary files.
        record = read_json(output / 'run.json')
        mapping = read_json(output / 'timeline.json')
        if not isinstance(record, dict) or not isinstance(mapping, dict):
            raise ValueError('run.json and timeline.json must be objects')
        if record.get('status') != 'verified' or not record.get('output_sha256'):
            raise ValueError('render did not complete successfully')
        if not isinstance(record.get('artifact_sha256'), dict) or not isinstance(record.get('media'), dict):
            raise ValueError('run.json contains invalid artifact or media metadata')
        for name in ('plan.json', 'timeline.json', 'filter.ffscript'):
            if digest(output / name) != record.get('artifact_sha256', {}).get(name):
                raise ValueError(f'audit artifact changed: {name}')
        report = verify_media(output / 'output.mp4', record['media'], mapping,
                              binary(ffmpeg), binary(ffprobe), runner, record['output_sha256'])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {'status': 'failed', 'errors': [str(exc)], 'review_status': 'pending_human_review'}
    report['commands'] = runner.record['commands']
    if output.is_dir():
        write_json(output / 'verification.json', report)
    return report
