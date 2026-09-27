"""Show the hot-titles chart and how much of it is watchable.

Read-only unless ``--refresh`` (stores a rebuilt chart) or ``--complete N``
(runs the completion lane inline, same as the beat tick).

    manage.py hot_titles                 # stored chart, or a live build if none
    manage.py hot_titles --live --top 15 # build from TMDB now, store nothing
"""

from django.core.management.base import BaseCommand

from apps.catalog import hot_titles


class Command(BaseCommand):
    help = "Show this week's hot-titles chart (TMDB trending/now playing/new) and its catalog coverage."

    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true', help='Build from TMDB now; store nothing.')
        parser.add_argument('--refresh', action='store_true', help='Rebuild and store the chart.')
        parser.add_argument('--complete', type=int, default=0, help='Complete up to N titles inline.')
        parser.add_argument('--top', type=int, default=10, help='Rows to print per kind.')

    def handle(self, *args, **options):
        if options['refresh']:
            self.stdout.write(f"REFRESH {hot_titles.refresh_hot_chart(force=True)}")
        chart = None if options['live'] else hot_titles.get_hot_chart()
        source = 'stored'
        if chart is None:
            chart, source = hot_titles.build_hot_chart(), 'live'
        age = hot_titles.chart_age_hours(chart)
        self.stdout.write(f"CHART source={source} age_hours={round(age or 0, 2)} feeds={chart.get('feeds')}")

        from apps.catalog.models import Movie, Series

        for kind, model in (('movie', Movie), ('series', Series)):
            rows = chart.get(kind) or []
            held = {
                obj.tmdb_id: obj
                for obj in model.objects.filter(tmdb_id__in=[row['tmdb_id'] for row in rows])
            }
            self.stdout.write(f'{kind.upper()} ({len(rows)})')
            for row in rows[: max(0, options['top'])]:
                obj = held.get(row['tmdb_id'])
                state = 'missing' if obj is None else ('watchable' if hot_titles._is_watchable(obj) else 'draft')
                self.stdout.write(
                    f"  #{row['rank']:<3} {row['score']:<6} {row['released']} tmdb={row['tmdb_id']:<8} "
                    f"{state:<9} {row.get('original_title') or row.get('title')} [{','.join(row.get('signals') or [])}]"
                )
        self.stdout.write(f'COVERAGE {hot_titles.coverage(chart)}')

        if options['complete']:
            result = hot_titles.complete_hot_titles(limit=options['complete'], chart=chart)
            self.stdout.write(f"COMPLETE { {k: v for k, v in result.items() if k != 'errors'} }")
