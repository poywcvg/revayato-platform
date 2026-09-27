"""Read-only health report for viewer-reported playback subtitle gaps.

Answers "when a viewer opens a title without Persian subtitles, how often do we
fix it, how fast, and where do the rest get stuck?". Never writes.

    python manage.py subtitle_gap_report
    python manage.py subtitle_gap_report --days 3 --top 30
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone


class Command(BaseCommand):
    help = 'Summarise PlaybackSubtitleGap outcomes (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7)
        parser.add_argument('--top', type=int, default=20)

    def handle(self, *args, **options):
        from apps.catalog.models import PlaybackSubtitleGap

        since = timezone.now() - timedelta(days=max(1, options['days']))
        rows = PlaybackSubtitleGap.objects.filter(updated_at__gte=since)
        out = self.stdout.write
        out(f'window: last {options["days"]}d  total gaps touched: {rows.count()}')
        out(f'all-time gaps: {PlaybackSubtitleGap.objects.count()}')

        out('\nstatus x last_result:')
        for row in rows.values('status', 'last_result').annotate(n=Count('id')).order_by('-n'):
            out(f'  {row["status"]:<12} {row["last_result"] or "-":<24} {row["n"]}')

        out('\ncontent_type x status:')
        for row in rows.values('content_type', 'status').annotate(n=Count('id')).order_by('content_type', '-n'):
            out(f'  {row["content_type"]:<8} {row["status"]:<12} {row["n"]}')

        resolved = rows.filter(status=PlaybackSubtitleGap.Status.RESOLVED, resolved_at__isnull=False)
        latencies = sorted(
            (gap.resolved_at - gap.created_at).total_seconds()
            for gap in resolved.only('created_at', 'resolved_at')
        )
        if latencies:
            def pct(p):
                return latencies[min(len(latencies) - 1, int(len(latencies) * p))]
            out(
                f'\nresolve latency (s, from first report): n={len(latencies)} '
                f'p50={pct(.5):.0f} p75={pct(.75):.0f} p90={pct(.9):.0f}'
            )
            buckets = Counter()
            for sec in latencies:
                if sec <= 10:
                    buckets['<=10s'] += 1
                elif sec <= 60:
                    buckets['<=1m'] += 1
                elif sec <= 600:
                    buckets['<=10m'] += 1
                elif sec <= 3600:
                    buckets['<=1h'] += 1
                else:
                    buckets['>1h'] += 1
            out('  ' + '  '.join(f'{k}:{buckets[k]}' for k in ['<=10s', '<=1m', '<=10m', '<=1h', '>1h']))

        meta_flags = Counter()
        for gap in rows.exclude(status=PlaybackSubtitleGap.Status.RESOLVED).only('meta', 'playback_version'):
            meta = gap.meta or {}
            meta_flags[f'version={gap.playback_version or "-"}'] += 1
            for key in ('prefer_embedded', 'allow_ffmpeg', 'hardsub_lane', 'soft_only'):
                if meta.get(key):
                    meta_flags[key] += 1
            if meta.get('drain_count'):
                meta_flags[f'drain_count={meta.get("drain_count")}'] += 1
            if meta.get('exhausted_count'):
                meta_flags['exhausted_before'] += 1
        out('\nunresolved gap traits:')
        for key, n in meta_flags.most_common():
            out(f'  {key:<28} {n}')

        out(f'\ntop {options["top"]} unresolved by viewer reports:')
        top = rows.exclude(status=PlaybackSubtitleGap.Status.RESOLVED).order_by('-report_count')[: options['top']]
        for gap in top:
            age_h = (timezone.now() - gap.created_at).total_seconds() / 3600
            out(
                f'  #{gap.pk:<6} {gap.content_type:<6} obj={gap.object_id:<6} ep={gap.episode_id:<7} '
                f'reports={gap.report_count:<4} {gap.status:<11} {gap.last_result or "-":<20} '
                f'age={age_h:5.1f}h  {gap.slug[:40]}'
            )
