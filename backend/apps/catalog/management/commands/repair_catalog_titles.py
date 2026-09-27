"""Give every movie and series a real Persian title and an English title.

    repair_catalog_titles --report            # counts only, no network, no writes
    repair_catalog_titles --limit 150         # fix broken titles, then upgrade machine ones
    repair_catalog_titles --scope all         # also re-check every row against TMDB's English

See :mod:`apps.catalog.title_repair` for the source order.
"""

from __future__ import annotations

import time
from collections import Counter

from django.core.management.base import BaseCommand

from apps.catalog.models import Movie, Series
from apps.catalog.title_repair import (
    _recently_checked,
    broken_titles_q,
    repair_titles,
    title_problem,
    weak_titles_q,
)

_FIELDS = ('id', 'title', 'original_title', 'source_metadata', 'tmdb_id', 'imdb_id', 'is_published', 'updated_at')
# How long a row that was just checked rests before the same scope looks again.
_RECHECK_HOURS = {'broken': 6.0, 'weak': 24.0 * 30, 'all': 24.0 * 30}


def _fields(model):
    extra = [name for name in ('manual_override_fields', 'meta_title') if hasattr(model, name)]
    return [*_FIELDS, *extra]


class Command(BaseCommand):
    help = 'Report or repair Persian (title) and English (original_title) titles of movies and series.'

    def add_arguments(self, parser):
        parser.add_argument('--report', action='store_true', help='Count problems only (no network, no writes).')
        parser.add_argument(
            '--scope', choices=['broken', 'weak', 'all'], action='append',
            help='broken = no Persian / no English title; weak = machine-translated title; '
                 'all = every row. Repeatable; default: broken then weak.',
        )
        parser.add_argument('--limit', type=int, default=0, help='Rows to check per run (0 = no limit).')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--no-translate', action='store_true', help='Never fall back to machine translation.')
        parser.add_argument('--sleep', type=float, default=0.2, help='Pause between rows that hit the network.')
        parser.add_argument('--show', type=int, default=20, help='Print this many changes.')

    def _models(self, options):
        models = []
        if not options['series_only']:
            models.append(Movie)
        if not options['movies_only']:
            models.append(Series)
        return models

    def handle(self, *args, **options):
        if options['report']:
            return self._report(options)
        from apps.catalog.tmdb import configured_tmdb_client

        try:
            client = configured_tmdb_client()
        except Exception as exc:  # no TMDB: Wikidata + translation still work
            self.stderr.write(f'TMDB unavailable ({exc}); continuing without it.')
            client = None
        scopes = options['scope'] or ['broken', 'weak']
        limit = max(0, int(options['limit'] or 0))
        stats = Counter()
        shown = 0
        for scope in scopes:
            for model in self._models(options):
                qs = model.objects.only(*_fields(model))
                if scope == 'broken':
                    qs = qs.filter(broken_titles_q())
                elif scope == 'weak':
                    qs = qs.filter(weak_titles_q())
                # Published rows are what viewers see; fix those first.
                for obj in qs.order_by('-is_published', 'id').iterator(chunk_size=500):
                    if limit and stats['checked'] >= limit:
                        break
                    if scope == 'broken' and not title_problem(obj).startswith('missing_'):
                        continue
                    if _recently_checked(obj, hours=_RECHECK_HOURS[scope]):
                        continue
                    stats['checked'] += 1
                    try:
                        result = repair_titles(
                            obj, client=client, translate=not options['no_translate'],
                            dry_run=options['dry_run'],
                        )
                    except Exception as exc:
                        stats['errors'] += 1
                        self.stderr.write(f'{model.__name__}#{obj.pk}: {exc.__class__.__name__}: {exc}')
                        continue
                    changes = result['changed']
                    if 'title' in changes:
                        stats[f"persian_from_{result['persian_source']}"] += 1
                    if 'original_title' in changes:
                        stats['english_fixed'] += 1
                    for name in result['unresolved']:
                        stats[f'unresolved_{name}'] += 1
                    if changes and shown < options['show']:
                        shown += 1
                        self.stdout.write(f'  {model.__name__}#{obj.pk} ' + '; '.join(
                            f'{field}: {old!r} → {new!r}' for field, (old, new) in changes.items()
                        ) + f" [{result['persian_source']}]")
                    if changes:
                        stats['changed'] += 1
                    if options['sleep']:
                        time.sleep(options['sleep'])
        if stats['changed'] and not options['dry_run']:
            from apps.catalog.cache import bump_catalog_cache_version

            bump_catalog_cache_version()
        self.stdout.write(
            f"repair_catalog_titles {'dry-run ' if options['dry_run'] else ''}done: "
            + ' '.join(f'{key}={value}' for key, value in sorted(stats.items()))
        )

    def _report(self, options):
        for model in self._models(options):
            counts = Counter()
            sources = Counter()
            for obj in model.objects.only(*_fields(model)).iterator(chunk_size=1000):
                bucket = 'published' if obj.is_published else 'draft'
                counts[f'{bucket}_total'] += 1
                problem = title_problem(obj)
                if problem:
                    counts[f'{bucket}_{problem}'] += 1
                if obj.is_published:
                    sources[((obj.source_metadata or {}).get('title_source') or 'unknown')] += 1
            self.stdout.write(f'{model.__name__}: ' + ' '.join(f'{k}={v}' for k, v in sorted(counts.items())))
            self.stdout.write('  published title sources: ' + ' '.join(f'{k}={v}' for k, v in sources.most_common()))
