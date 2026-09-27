"""Answer & remediate open support tickets from the CLI.

Examples::

    python3 manage.py resolve_support_tickets --dry-run
    python3 manage.py resolve_support_tickets --limit 20
    python3 manage.py resolve_support_tickets --ticket RVT-ABC123
    python3 manage.py resolve_support_tickets --category content_request
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.engagement.support_automation import resolve_open_tickets


class Command(BaseCommand):
    help = 'Automatically answer and remediate open support tickets (درخواست‌ها).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)
        parser.add_argument('--dry-run', action='store_true', help='Decide but write nothing.')
        parser.add_argument('--ticket', type=str, default=None, help='Only this tracking code.')
        parser.add_argument('--category', type=str, default=None, help='Only this category.')

    def handle(self, *args, **options):
        stats = resolve_open_tickets(
            limit=options['limit'],
            dry_run=options['dry_run'],
            category=options['category'],
            ticket_code=options['ticket'],
        )
        tag = ' [dry-run]' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f"Support automation{tag}: processed={stats['processed']} "
            f"resolved={stats['resolved']} in_progress={stats['in_progress']} "
            f"waiting_user={stats['waiting_user']} errors={stats['errors']}"
        ))
        for row in stats['outcomes']:
            self.stdout.write(
                f"  · {row['tracking_code']} [{row['category']}] → {row['status']} ({row['action']})"
            )
        if options.get('verbosity', 1) >= 2:
            self.stdout.write(json.dumps(stats, ensure_ascii=False, indent=2))
