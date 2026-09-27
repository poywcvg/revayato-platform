"""Auto-fix viewer-reported content issues.

Drains open :class:`~apps.catalog.models.ContentIssueReport` rows through the
remediation engine, which dispatches each ``problem_type`` to the crawler or
classifier that already fixes it (subtitle pipeline, playback-source re-crawl,
link-integrity strip + re-import). Most-reported titles first.

Examples::

    python manage.py remediate_content_reports --dry-run
    python manage.py remediate_content_reports --limit 50
    python manage.py remediate_content_reports --problem wrong_title
    python manage.py remediate_content_reports --report-id 42 --force
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Automatically remediate viewer-reported content issues.'

    def add_arguments(self, parser):
        parser.add_argument('--report-id', type=int, default=None, help='Remediate a single report by id')
        parser.add_argument('--limit', type=int, default=25, help='Max reports to drain (batch mode)')
        parser.add_argument('--problem', type=str, default=None, help='Restrict to one problem_type')
        parser.add_argument('--max-attempts', type=int, default=3, help='Skip queued rows past this many attempts')
        parser.add_argument('--force', action='store_true', help='Re-run even resolved/rejected (single-report mode)')
        parser.add_argument('--dry-run', action='store_true', help='List what would run without touching providers')

    def handle(self, *args, **options):
        from apps.catalog.content_remediation import remediate_open_reports, remediate_report
        from apps.catalog.models import ContentIssueReport

        report_id = options.get('report_id')
        if report_id:
            report = ContentIssueReport.objects.filter(pk=report_id).first()
            if report is None:
                raise CommandError(f'No ContentIssueReport with id={report_id}')
            if options.get('dry_run'):
                self.stdout.write(f'DRY RUN: would remediate #{report.pk} ({report.problem_type}, {report.status}).')
                return
            outcome = remediate_report(report, force=bool(options.get('force')))
            self.stdout.write(
                f'#{outcome.get("report_id")} → {outcome.get("status")} '
                f'[{outcome.get("action", "-")}] {outcome.get("result", "")}'.strip()
            )
            return

        stats = remediate_open_reports(
            limit=int(options.get('limit') or 25),
            problem_type=options.get('problem'),
            max_attempts=int(options.get('max_attempts') or 3),
            dry_run=bool(options.get('dry_run')),
        )
        if options.get('dry_run'):
            self.stdout.write(f'DRY RUN: {stats["processed"]} open report(s) would be remediated.')
            return
        self.stdout.write(
            'remediated {processed} report(s): {resolved} resolved, {queued} queued, '
            '{needs_review} need review, {other} other.'.format_map(stats)
        )
