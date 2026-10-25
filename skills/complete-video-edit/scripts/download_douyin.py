"""Optional Douyin backend adapter; media validation is required before success."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REVISION = '427f5fd190ea754a09883273bc38379eb4fd924e'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('share', help='Douyin URL or full share text')
    p.add_argument('--backend', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True, help='New directory only')
    p.add_argument('--ffprobe', required=True)
    p.add_argument('--ffmpeg', required=True)
    a = p.parse_args()
    backend = a.backend.resolve()
    revision = subprocess.check_output(['git', '-C', str(backend), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('Backend revision differs from tested version; review before use')
    sys.path.insert(0, str(backend))
    from douyin_parser import parse
    import requests
    a.output.mkdir(parents=True, exist_ok=False)
    record = {'status': 'failed', 'backend_revision': revision}
    try:
        data = parse(a.share)
        if data.get('type') != 'video':
            raise ValueError('This adapter handles single videos only')
        record.update(id=data['aweme_id'], title=data['title'],
                      source_url='https://www.douyin.com/video/' + data['aweme_id'])
        choices = sorted(data.get('qualities') or [],
                         key=lambda q: (q.get('resolution', 0), q.get('bit_rate', 0)), reverse=True)
        urls = []
        if choices:
            q = choices[0]
            urls = q.get('urls') or [q.get('url')]
            record['quality_label'] = q.get('label')
        urls = urls or data.get('video_urls', [])
        partial = a.output / 'video.part.mp4'
        for url in list(dict.fromkeys(u for u in urls if u))[:3]:
            try:
                with requests.get(url, headers={'Referer': 'https://www.douyin.com/',
                                               'User-Agent': 'Mozilla/5.0'},
                                  stream=True, timeout=(15, 30)) as response:
                    response.raise_for_status()
                    with partial.open('wb') as f:
                        for chunk in response.iter_content(1024 * 1024):
                            f.write(chunk)
                probe = subprocess.run([a.ffprobe, '-v', 'error', '-show_format', '-show_streams',
                                        '-of', 'json', str(partial)], capture_output=True, text=True, encoding='utf-8', timeout=60)
                probe.check_returncode()
                info = json.loads(probe.stdout)
                if not any(s.get('codec_type') == 'video' for s in info['streams']):
                    raise ValueError('No video stream')
                duration = float(info['format']['duration'])
                if duration <= 0 or (data.get('duration') and abs(duration - data['duration']) > 2):
                    raise ValueError('Duration does not match source metadata')
                subprocess.run([a.ffmpeg, '-v', 'error', '-xerror', '-i', str(partial),
                                '-f', 'null', '-'], capture_output=True, check=True, timeout=600)
                destination = a.output / 'video.mp4'
                partial.rename(destination)
                record.update(status='verified', duration=duration, streams=info['streams'],
                              size=destination.stat().st_size,
                              sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
                print(str(destination.resolve()))
                return
            except (requests.RequestException, subprocess.SubprocessError, ValueError, KeyError):
                continue
        raise RuntimeError('No candidate produced a complete decodable video')
    except Exception as exc:
        record['error_type'] = type(exc).__name__
        raise RuntimeError('Download failed; inspect status and platform access, do not assume success') from None
    finally:
        (a.output / 'download-record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
