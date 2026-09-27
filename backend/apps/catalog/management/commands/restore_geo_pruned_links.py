"""Put back mirrors the media check pruned while it misread geo blocks as dead.

Until 2026-09-25 the probe judged an HTML answer on its first 2 KB. The myf2m
CDN (abrtech.top → mehracdn.com) answers non-Iranian IPs with a "turn your VPN
off" page whose words start near byte 3000, so every such mirror read as
``html_not_video`` and was pruned — and a title left with nothing was sent to
draft. The pruned URLs survive only in each title's last ``MediaCheck`` probe
list; this command reads them back from there.

Nothing is restored on trust. Each URL is probed again with the fixed probe and
kept only when it now answers live or geo-blocked, then goes through the same
storage guards as any crawled link (identity check + media screen). Publishing
is left to the importer's normal gate. Dry run unless ``--apply``.
"""

from django.core.management.base import BaseCommand

MAX_URLS_PER_TITLE = 24


class Command(BaseCommand):
    help = 'Restore mirrors wrongly pruned as html_not_video (geo-blocked CDN pages).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write links back (default: dry run).')
        parser.add_argument('--limit', type=int, default=200, help='Titles to handle this run.')
        parser.add_argument('--top250', action='store_true', help='Only IMDb Top 250 chart titles.')

    def handle(self, *args, **options):
        from apps.catalog import media_probe
        from apps.catalog.models import ImdbChartEntry, MediaCheck, Movie, Series
        from apps.catalog.provider_import.link_apply import apply_provider_download_links

        models = {'movie': Movie, 'series': Series}
        pruned: dict[tuple[str, int], list[str]] = {}
        checks = MediaCheck.objects.filter(
            content_type__in=list(models), detail__icontains='html_not_video',
        ).only('content_type', 'object_id', 'detail')
        for check in checks.iterator():
            urls = [
                row.get('url') for row in (check.detail or {}).get('probes', [])
                if row.get('verdict') == 'dead' and row.get('reason') == 'html_not_video' and row.get('url')
            ]
            if urls:
                bucket = pruned.setdefault((check.content_type, check.object_id), [])
                bucket.extend(url for url in urls if url not in bucket)

        if options['top250']:
            chart = set(ImdbChartEntry.objects.filter(movie__isnull=False).values_list('movie_id', flat=True))
            chart_series = set(ImdbChartEntry.objects.filter(series__isnull=False).values_list('series_id', flat=True))
            pruned = {
                key: urls for key, urls in pruned.items()
                if key[1] in (chart if key[0] == 'movie' else chart_series)
            }

        stats = {'titles': 0, 'candidates': 0, 'restorable': 0, 'restored_titles': 0, 'errors': 0}
        # Unpublished titles first: they are the ones this misjudgement took offline.
        ordered = sorted(pruned.items(), key=lambda item: item[0][1])
        for (kind, pk), urls in ordered:
            if stats['titles'] >= options['limit']:
                break
            obj = models[kind].objects.filter(pk=pk).first()
            if obj is None:
                continue
            present = {
                str(item.get('url') or '').strip()
                for item in (obj.download_links or []) if isinstance(item, dict)
            }
            missing = [url for url in urls if url not in present][:MAX_URLS_PER_TITLE]
            if not missing:
                continue
            stats['titles'] += 1
            stats['candidates'] += len(missing)
            back = []
            for url in missing:
                probe = media_probe.probe_url(url, use_cache=False)
                if probe.live or probe.reason == 'geo_blocked':
                    back.append({'url': url})
            stats['restorable'] += len(back)
            self.stdout.write(
                f'RESTORE kind={kind} pk={pk} published={obj.is_published} '
                f'missing={len(missing)} restorable={len(back)} title={obj.title}'
            )
            if not back or not options['apply']:
                continue
            try:
                apply_provider_download_links(obj, back, replace=False)
                stats['restored_titles'] += 1
            except Exception as exc:  # one title must not end the run
                stats['errors'] += 1
                self.stderr.write(f'RESTORE_FAILED kind={kind} pk={pk}: {str(exc)[:200]}')

        mode = 'APPLIED' if options['apply'] else 'DRY_RUN'
        self.stdout.write(f'RESTORE_{mode} ' + ' '.join(f'{k}={v}' for k, v in stats.items()))
