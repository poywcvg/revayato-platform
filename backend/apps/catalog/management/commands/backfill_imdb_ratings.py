"""Backfill verified IMDb ratings via OMDb for titles that have an imdb_id.

Requires OMDB_API_KEY. Never copies TMDB vote_average into imdb_rating.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import Movie, Series
from apps.catalog.ratings import _as_float, _as_int, _fetch_omdb_by_imdb_id, _cache_key
from django.core.cache import cache


class Command(BaseCommand):
    help = 'Fetch real IMDb ratings from OMDb for movies/series with an imdb_id.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max titles to process (0 = all).')
        parser.add_argument('--sleep', type=float, default=0.35, help='Delay between OMDb calls.')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--force', action='store_true', help='Re-fetch even when imdb_rating_source is omdb.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if not (getattr(settings, 'OMDB_API_KEY', '') or '').strip():
            raise CommandError(
                'OMDB_API_KEY is empty. Add it to .env.production, recreate backend, then re-run.'
            )

        limit = max(0, int(options['limit'] or 0))
        sleep_s = max(0.0, float(options['sleep'] or 0))
        force = bool(options['force'])
        dry_run = bool(options['dry_run'])

        targets = []
        if not options['series_only']:
            targets.append(('movie', Movie.objects.filter(is_published=True).exclude(Q(imdb_id__isnull=True) | Q(imdb_id=''))))
        if not options['movies_only']:
            targets.append(('series', Series.objects.filter(is_published=True).exclude(Q(imdb_id__isnull=True) | Q(imdb_id=''))))

        updated = skipped = failed = 0
        processed = 0

        for media_type, queryset in targets:
            for obj in queryset.iterator(chunk_size=50):
                if limit and processed >= limit:
                    break
                processed += 1
                imdb_id = (obj.imdb_id or '').strip()
                if not imdb_id.startswith('tt'):
                    skipped += 1
                    continue

                meta = dict(obj.source_metadata or {})
                if not force and meta.get('imdb_rating_source') == 'omdb' and obj.imdb_rating is not None:
                    skipped += 1
                    continue

                payload = _fetch_omdb_by_imdb_id(imdb_id)
                if not payload:
                    failed += 1
                    self.stderr.write(f'OMDb miss {media_type}#{obj.pk} {imdb_id}')
                    if sleep_s:
                        time.sleep(sleep_s)
                    continue

                score = _as_float(payload.get('imdbRating'))
                if score is None or score <= 0:
                    failed += 1
                    if sleep_s:
                        time.sleep(sleep_s)
                    continue

                votes = _as_int(str(payload.get('imdbVotes') or '').replace(',', '').strip())
                meta['imdb_rating'] = score
                meta['imdb_votes'] = votes
                meta['imdb_rating_source'] = 'omdb'
                meta['imdb_rating_fetched_at'] = timezone.now().isoformat()

                if dry_run:
                    self.stdout.write(f'[dry-run] {media_type}#{obj.pk} {imdb_id} -> {score}')
                    updated += 1
                else:
                    obj.imdb_rating = round(score, 1)
                    obj.source_metadata = meta
                    obj.save(update_fields=['imdb_rating', 'source_metadata', 'updated_at'])
                    cache.delete(_cache_key(media_type, int(obj.pk)))
                    updated += 1
                    self.stdout.write(f'{media_type}#{obj.pk} {imdb_id} -> {score}')

                if sleep_s:
                    time.sleep(sleep_s)

            if limit and processed >= limit:
                break

        self.stdout.write(self.style.SUCCESS(
            f'Done. updated={updated} skipped={skipped} failed={failed} dry_run={dry_run}'
        ))
