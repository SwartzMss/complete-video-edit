"""Validate and execute a deletion-only edit plan; JSON output, nonzero on failure."""
import argparse
import json
import sys

from editing import pipeline


def main():
    # Windows consoles/pipes must not corrupt Chinese paths or audit reasons.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('check', 'render', 'verify'):
        command = commands.add_parser(name)
        command.add_argument('input', help='Plan JSON' if name != 'verify' else 'Result directory')
        command.add_argument('--ffprobe', default='ffprobe')
        if name != 'check':
            command.add_argument('--ffmpeg', default='ffmpeg')
        if name == 'render':
            command.add_argument('--output', required=True, help='New result directory only')
    args = parser.parse_args()
    try:
        if args.command == 'check':
            result = pipeline.check(args.input, args.ffprobe)
        elif args.command == 'render':
            result = pipeline.render(args.input, args.output, args.ffmpeg, args.ffprobe)
        else:
            result = pipeline.verify(args.input, args.ffmpeg, args.ffprobe)
    except (Exception, KeyboardInterrupt) as exc:
        result = {'status': 'failed', 'error': str(exc) or type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    sys.exit(main())
