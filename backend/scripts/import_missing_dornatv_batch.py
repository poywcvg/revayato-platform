#!/usr/bin/env python3
"""CLI wrapper: import missing Dornatv titles into the catalog."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from apps.catalog.provider_import.dornatv_import import run_dornatv_missing_import

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--movies-limit', type=int, default=50)
    parser.add_argument('--series-limit', type=int, default=20)
    parser.add_argument('--delay', type=float, default=0.35)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--checkpoint', default='/app/media/dornatv_import_checkpoint.json')
    parser.add_argument(
        '--year-start',
        type=int,
        default=None,
        help='Newest release year to walk (default: settings / 2026).',
    )
    parser.add_argument(
        '--year-end',
        type=int,
        default=None,
        help='Oldest release year to walk (default: settings / 1970).',
    )
    args = parser.parse_args()
    result = run_dornatv_missing_import(
        movies_limit=args.movies_limit,
        series_limit=args.series_limit,
        delay=args.delay,
        dry_run=args.dry_run,
        checkpoint_path=args.checkpoint,
        year_start=args.year_start,
        year_end=args.year_end,
    )
    print(result, flush=True)
    return 0 if result.get('status') in {'ok', 'rate_limited', 'dry_keep'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
