#!/usr/bin/env python3
"""Inspect registered assets without modifying, downloading or uploading them."""
import argparse
import json
import sys
from pathlib import Path

from asset_inventory import inventory, text_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / 'assets',
                        help='asset directory to scan (default: this installed Skill/assets)')
    parser.add_argument('--json', action='store_true', help='print versioned JSON instead of text')
    parser.add_argument('--decode', action='store_true', help='decode at most the first second with FFmpeg')
    parser.add_argument('--ffprobe', default='ffprobe', help='FFprobe executable name or path')
    parser.add_argument('--ffmpeg', default='ffmpeg', help='FFmpeg executable name or path')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    report = inventory(args.root, args.ffprobe, args.ffmpeg, args.decode)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) if args.json else text_report(report))
    return int(report['summary']['errors'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
