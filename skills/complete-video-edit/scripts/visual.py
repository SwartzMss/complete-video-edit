"""Optional photo-effect preparation/rendering; does not change edit-plan v1."""
import argparse
import json
import sys

from editing import visual_pipeline


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'render'):
        command = commands.add_parser(name)
        command.add_argument('input', help='Visual plan JSON' if name == 'prepare' else 'Prepared workspace')
        command.add_argument('--output', required=True, help='New directory only')
        command.add_argument('--ffmpeg', default='ffmpeg')
        command.add_argument('--ffprobe', default='ffprobe')
        if name == 'render':
            command.add_argument('--node', default='node')
            command.add_argument('--start-frame', type=int, default=0)
            command.add_argument('--end-frame', type=int, help='Exclusive end frame')
            command.add_argument('--stills', action='store_true', help='Also render phase keyframes')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = visual_pipeline.prepare(args.input, args.output, args.ffmpeg, args.ffprobe)
        else:
            result = visual_pipeline.render(args.input, args.output, args.ffmpeg, args.ffprobe, args.node,
                                            args.start_frame, args.end_frame, args.stills)
    except (Exception, KeyboardInterrupt) as exc:
        result = {'status': 'failed', 'error': str(exc) or type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return int(result['status'] == 'failed')


if __name__ == '__main__':
    sys.exit(main())
