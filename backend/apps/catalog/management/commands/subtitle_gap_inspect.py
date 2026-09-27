"""Read-only: explain why unresolved playback subtitle gaps are stuck.

For each unresolved gap prints the identity the crawlers search with (IMDb id,
original title, year, language), what kind of stream the viewer was on, and
which provider miss/circuit caches currently suppress a lookup. Never writes,
never calls a provider.

    python manage.py subtitle_gap_inspect --limit 60
    python manage.py subtitle_gap_inspect --ids 607 215
"""

from __future__ import annotations

import hashlib
from collections import Counter

from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Diagnose unresolved PlaybackSubtitleGap rows (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=60)
        parser.add_argument('--ids', type=int, nargs='*')
        parser.add_argument('--links', type=int, default=0, help='Also print N link basenames/labels per gap.')

    def handle(self, *args, **options):
        from apps.catalog.models import Episode, Movie, PlaybackSubtitleGap, Series
        from apps.catalog.subtitle_extract import (
            download_links_imply_dub,
            download_links_imply_hardsub,
            download_links_imply_softsub,
        )
        from apps.catalog.subtitle_star import normalize_imdb_id

        qs = PlaybackSubtitleGap.objects.exclude(status=PlaybackSubtitleGap.Status.RESOLVED)
        if options.get('ids'):
            qs = qs.filter(pk__in=options['ids'])
        qs = qs.order_by('-report_count')[: options['limit']]

        tally = Counter()
        out = self.stdout.write
        out(
            f'star circuit={bool(cache.get("catalog:subtitlestar:circuit-open"))} '
            f'subzone circuit={bool(cache.get("catalog:subzone:circuit-open"))}'
        )
        for gap in qs:
            model = Movie if gap.content_type == 'movie' else Series
            obj = model.objects.filter(pk=gap.object_id).first()
            if obj is None:
                out(f'#{gap.pk} object missing')
                tally['object_missing'] += 1
                continue
            imdb = normalize_imdb_id(getattr(obj, 'imdb_id', ''))
            year = getattr(obj, 'release_year', None) or getattr(obj, 'start_year', None)
            orig = str(getattr(obj, 'original_title', '') or '')
            lang = str(getattr(obj, 'original_language', '') or '')
            links = [row for row in (obj.download_links or []) if isinstance(row, dict)]
            kinds = []
            if download_links_imply_softsub(links):
                kinds.append('soft')
            if download_links_imply_hardsub(links):
                kinds.append('hard')
            if download_links_imply_dub(links):
                kinds.append('dub')
            ep = ''
            ep_video = ''
            if gap.episode_id:
                episode = Episode.objects.filter(pk=gap.episode_id).select_related('season').first()
                if episode is None:
                    ep = 'ep-missing'
                    tally['episode_missing'] += 1
                else:
                    ep = f's{episode.season.season_number}e{episode.episode_number}'
                    ep_video = 'video' if episode.video_url else 'no-video'
            identity = imdb or hashlib.sha256(f'{orig}|{year}'.encode()).hexdigest()[:24]
            prefix = 'series-miss' if gap.content_type == 'series' else 'miss'
            misses = [
                name for name, key in (
                    ('star', f'catalog:subtitlestar:{prefix}:{identity}'),
                    ('subzone', f'catalog:subzone:{prefix}:{identity}'),
                ) if cache.get(key)
            ]
            if not imdb:
                tally['no_imdb'] += 1
            if lang == 'fa':
                tally['persian_original'] += 1
            if not links:
                tally['no_links'] += 1
            tally[f'lang={lang or "-"}'] += 1
            tally[f'version={gap.playback_version or "-"}'] += 1
            out(
                f'#{gap.pk:<5} {gap.content_type:<6} {gap.status:<11} {gap.last_result or "-":<18} '
                f'r={gap.report_count:<3} imdb={imdb or "-":<11} y={year or "-"} lang={lang or "-":<3} '
                f'ver={gap.playback_version or "-":<8} links={len(links):<3} kinds={",".join(kinds) or "-":<14} '
                f'{ep} {ep_video} miss={",".join(misses) or "-"} | {orig[:36]}'
            )
            for row in links[: options['links']]:
                url = str(row.get('url') or '')
                out(
                    f'      s={row.get("season")!s:<4} e={row.get("episode")!s:<4} '
                    f'q={str(row.get("quality") or "")[:10]:<10} label={str(row.get("label") or "")[:60]!r} '
                    f'| {url.rsplit("/", 2)[-2][:30] if url.count("/") > 3 else ""}/{url.rsplit("/", 1)[-1][:90]}'
                )
        out('\ntally: ' + '  '.join(f'{k}={v}' for k, v in tally.most_common()))
