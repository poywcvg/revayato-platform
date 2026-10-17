"""How many download / online-play links show their file size.

Read-only by default. ``--fill N`` runs the sizing sweep inline on N titles.

    manage.py link_sizes              # coverage of published movies + series
    manage.py link_sizes --fill 20    # measure the next 20 titles now
    manage.py link_sizes --hosts 15   # + which hosts answer with a size
    manage.py link_sizes --probe-refused HOST   # why HOST gives none (no writes)
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.catalog import link_sizes

_COVERAGE_SQL = """
SELECT count(*) AS links,
       count(*) FILTER (WHERE coalesce(l->>'size_label', '') <> '') AS sized,
       count(*) FILTER (WHERE coalesce(l->>'size_label', '') = ''
                          AND l ? 'size_probed_at') AS refused,
       count(DISTINCT t.id) FILTER (WHERE coalesce(l->>'size_label', '') = '') AS titles_missing,
       count(DISTINCT t.id) AS titles
FROM {table} t, jsonb_array_elements(t.download_links) l
WHERE t.is_published AND jsonb_typeof(t.download_links) = 'array'
  AND jsonb_typeof(l) = 'object'
"""


_HOSTS_SQL = """
SELECT split_part(split_part(l->>'url', '://', 2), '/', 1) AS host,
       count(*) FILTER (WHERE coalesce(l->>'size_label', '') <> '') AS sized,
       count(*) FILTER (WHERE coalesce(l->>'size_label', '') = '' AND l ? 'size_probed_at') AS refused,
       count(*) FILTER (WHERE coalesce(l->>'size_label', '') = '' AND NOT l ? 'size_probed_at') AS pending
FROM {table} t, jsonb_array_elements(t.download_links) l
WHERE t.is_published AND jsonb_typeof(t.download_links) = 'array'
  AND jsonb_typeof(l) = 'object'
GROUP BY 1 ORDER BY count(*) DESC LIMIT %s
"""


class Command(BaseCommand):
    help = 'Report (and optionally fill) file sizes on download / online-play links.'

    def add_arguments(self, parser):
        parser.add_argument('--fill', type=int, default=0, help='Measure up to N titles now.')
        parser.add_argument('--hosts', type=int, default=0, help='Also list the top N hosts.')
        parser.add_argument('--probe-refused', metavar='HOST', default='',
                            help='Re-probe a few refused links of HOST (no writes) and show why.')
        parser.add_argument('--budget', type=float, default=300.0, help='Seconds for --fill.')

    def handle(self, *args, **options):
        if options['probe_refused']:
            return self._probe_refused(options['probe_refused'])
        if options['fill']:
            result = link_sizes.fill_missing_sizes(limit=options['fill'], budget_seconds=options['budget'])
            self.stdout.write(f'FILL {result}')

        from apps.catalog.models import Movie, Series

        for model in (Movie, Series):
            # One scan of every link array; allowed longer than the web's timeout.
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '180s'")
                cursor.execute(_COVERAGE_SQL.format(table=model._meta.db_table))
                links, sized, refused, missing_titles, titles = cursor.fetchone()
                hosts = []
                if options['hosts']:
                    cursor.execute(_HOSTS_SQL.format(table=model._meta.db_table), [options['hosts']])
                    hosts = cursor.fetchall()
            share = round(100.0 * sized / links, 1) if links else 0.0
            self.stdout.write(
                f'{model.__name__.upper()} links={links} sized={sized} ({share}%) '
                f'refused={refused} titles_missing_some={missing_titles}/{titles}'
            )
            for host, h_sized, h_refused, h_pending in hosts:
                self.stdout.write(f'  {host:<40} sized={h_sized:<6} refused={h_refused:<6} pending={h_pending}')

    def _probe_refused(self, host: str, sample: int = 6) -> None:
        from apps.catalog.media_probe import probe_url
        from apps.catalog.models import Movie, Series

        for model in (Movie, Series):
            seen = 0
            for links in model.objects.filter(is_published=True).order_by('-popularity') \
                    .values_list('download_links', flat=True).iterator(chunk_size=50):
                for item in links or []:
                    if not isinstance(item, dict) or item.get('size_label') or not item.get('size_probed_at'):
                        continue
                    url = str(item.get('url') or '')
                    if f'//{host}/' not in url:
                        continue
                    probe = probe_url(url, expect='video', use_cache=False)
                    self.stdout.write(
                        f'{model.__name__} {probe.status} {probe.verdict} reason={probe.reason or "-"} '
                        f'type={probe.content_type} len={probe.content_length} '
                        f'path=...{url.split("?")[0][-60:]}'
                    )
                    seen += 1
                    if seen >= sample:
                        break
                if seen >= sample:
                    break
