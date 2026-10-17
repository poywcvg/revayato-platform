"""جدول پخش: TMDB release dates → AiringEntry → the hunter that puts them on the site."""

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from . import airing
from .models import AiringEntry, Episode, Movie, Season, Series
from .schedule import build_weekly_schedule

TODAY = airing.today_tehran()
NOW = timezone.now()


class FakeTMDB:
    def __init__(self, series=None, seasons=None, releases=None):
        self.series = series or {}
        self.seasons = seasons or {}
        self.releases = releases or {}
        self.calls = []

    def _request(self, path, params=None, **kwargs):
        self.calls.append(path)
        kind, tmdb_id, *rest = path.split('/')
        if kind == 'movie':
            return self.releases[int(tmdb_id)]
        return self.series[int(tmdb_id)]

    def tv_season_details(self, tmdb_id, season_number):
        self.calls.append(f'season/{tmdb_id}/{season_number}')
        return self.seasons[(int(tmdb_id), int(season_number))]

    def image_url(self, path, size='w500'):
        return f'https://image.tmdb.org/t/p/{size}{path}' if path else ''


def _ep(number, aired, **extra):
    return {'episode_number': number, 'air_date': aired.isoformat(), 'name': f'Chapter {number}', **extra}


class _Case(TestCase):
    def setUp(self):
        cache.clear()
        self.series = Series.objects.create(
            title='سریال', original_title='Show', slug='show-2025', tmdb_id=500,
            status=Series.Status.ONGOING, is_published=True, popularity=50,
        )

    def tmdb(self, episodes, *, season=2):
        return FakeTMDB(
            series={500: {
                'status': 'Returning Series', 'networks': [{'name': 'HBO'}],
                'next_episode_to_air': {'season_number': season, 'episode_number': 3, 'air_date': (TODAY + timedelta(days=2)).isoformat()},
                'last_episode_to_air': {'season_number': season, 'episode_number': 2, 'air_date': (TODAY - timedelta(days=5)).isoformat()},
                'seasons': [{'season_number': 0, 'air_date': '2020-01-01'}, {'season_number': season, 'air_date': (TODAY - timedelta(days=12)).isoformat()}],
            }},
            seasons={(500, season): {'episodes': episodes}},
        )

    def publish_episode(self, season_number, episode_number, title='قسمت 2'):
        season, _ = Season.objects.get_or_create(
            series=self.series, season_number=season_number, defaults={'title': 'فصل', 'is_published': True},
        )
        return Episode.objects.create(season=season, episode_number=episode_number, title=title, is_published=True)


class SyncTests(_Case):
    def test_episodes_get_real_dates_and_states(self):
        self.publish_episode(2, 1)
        client = self.tmdb([
            _ep(1, TODAY - timedelta(days=12)),
            _ep(2, TODAY - timedelta(days=5), episode_type='standard', still_path='/s.jpg', runtime=58),
            _ep(3, TODAY + timedelta(days=2)),
            _ep(8, TODAY + timedelta(days=37), episode_type='finale'),
            _ep(9, TODAY + timedelta(days=200)),  # outside the window
        ])
        stats = airing.sync_series(self.series, client, today=TODAY, now=NOW)
        self.assertEqual(stats['created'], 4)
        rows = {row.episode_number: row for row in AiringEntry.objects.all()}
        self.assertEqual(set(rows), {1, 2, 3, 8})
        self.assertEqual(rows[1].status, AiringEntry.Status.AVAILABLE)
        self.assertEqual(rows[1].release_type, 'premiere')
        self.assertEqual(rows[2].status, AiringEntry.Status.WAITING)
        self.assertEqual(rows[2].network, 'HBO')
        self.assertEqual(rows[2].runtime_minutes, 58)
        self.assertTrue(rows[2].still_url.endswith('/w300/s.jpg'))
        self.assertEqual(rows[3].status, AiringEntry.Status.UPCOMING)
        self.assertEqual(rows[3].next_hunt_at, airing.first_hunt_at(TODAY + timedelta(days=2)))
        self.assertEqual(rows[8].release_type, 'finale')
        # Specials (season 0) are never fetched.
        self.assertNotIn('season/500/0', client.calls)

    def test_redated_episode_moves_and_pulled_episode_is_dropped(self):
        airing.sync_series(self.series, self.tmdb([_ep(3, TODAY + timedelta(days=2)), _ep(4, TODAY + timedelta(days=9))]), today=TODAY, now=NOW)
        airing.sync_series(self.series, self.tmdb([_ep(3, TODAY + timedelta(days=4))]), today=TODAY, now=NOW)
        moved = AiringEntry.objects.get(episode_number=3)
        self.assertEqual(moved.air_date, TODAY + timedelta(days=4))
        self.assertEqual(moved.next_hunt_at, airing.first_hunt_at(TODAY + timedelta(days=4)))
        self.assertEqual(AiringEntry.objects.get(episode_number=4).status, AiringEntry.Status.DROPPED)

    def test_movie_uses_digital_not_theatrical_date(self):
        movie = Movie.objects.create(title='فیلم', original_title='Film', slug='film-2026', tmdb_id=77, release_date=TODAY - timedelta(days=40))
        client = FakeTMDB(releases={77: {'results': [
            {'iso_3166_1': 'FR', 'release_dates': [{'type': 4, 'release_date': (TODAY + timedelta(days=1)).isoformat() + 'T00:00:00.000Z'}]},
            {'iso_3166_1': 'US', 'release_dates': [
                {'type': 3, 'release_date': (TODAY - timedelta(days=40)).isoformat() + 'T00:00:00.000Z'},
                {'type': 4, 'release_date': (TODAY + timedelta(days=6)).isoformat() + 'T00:00:00.000Z'},
            ]},
        ]}})
        self.assertEqual(airing.sync_movie(movie, client, today=TODAY, now=NOW), 'created')
        entry = AiringEntry.objects.get(kind='movie')
        self.assertEqual(entry.air_date, TODAY + timedelta(days=6))
        self.assertEqual(entry.release_type, 'digital')

    def test_movie_without_digital_date_is_not_scheduled(self):
        movie = Movie.objects.create(title='فیلم', original_title='Film', slug='film-2027', tmdb_id=78, release_date=TODAY)
        client = FakeTMDB(releases={78: {'results': [{'iso_3166_1': 'US', 'release_dates': [{'type': 3, 'release_date': TODAY.isoformat()}]}]}})
        self.assertEqual(airing.sync_movie(movie, client, today=TODAY, now=NOW), 'outside')
        self.assertFalse(AiringEntry.objects.exists())

    def test_sync_pass_skips_titles_synced_recently(self):
        client = self.tmdb([_ep(3, TODAY + timedelta(days=2))])
        with mock.patch('apps.catalog.iranian.is_iranian_catalog_item', return_value=False):
            first = airing.sync_schedule(budget_seconds=60, client=client)
            calls = len(client.calls)
            second = airing.sync_schedule(budget_seconds=60, client=client)
        self.assertEqual(first['series'], 1)
        self.assertEqual(second['series'], 0)
        self.assertEqual(len(client.calls), calls)


class HuntTests(_Case):
    def entry(self, episode_number, aired, **extra):
        entry = AiringEntry(
            kind='episode', series=self.series, season_number=2, episode_number=episode_number, air_date=aired, **extra,
        )
        airing._initial_state(entry, timezone.now())
        entry.save()
        return entry

    def test_backoff_widens_then_gives_up(self):
        aired = TODAY - timedelta(days=1)
        start = airing.first_hunt_at(aired)
        self.assertEqual(airing.next_hunt_after(aired, start + timedelta(hours=1)) - (start + timedelta(hours=1)), timedelta(hours=2))
        self.assertEqual(airing.next_hunt_after(aired, start + timedelta(days=3)) - (start + timedelta(days=3)), timedelta(hours=6))
        self.assertEqual(airing.next_hunt_after(aired, start + timedelta(days=10)) - (start + timedelta(days=10)), timedelta(hours=24))
        self.assertIsNone(airing.next_hunt_after(aired, start + timedelta(days=22)))

    def test_crawl_that_lands_the_episode_marks_it_available(self):
        entry = self.entry(2, TODAY - timedelta(days=1))
        self.assertEqual(entry.status, AiringEntry.Status.WAITING)
        self.assertEqual(entry.title, '')
        entry.title = 'The Long Night'
        entry.save()

        def crawl(target, providers):
            self.publish_episode(2, 2)
            return 'crawled:4'

        with mock.patch.object(airing, '_crawl', side_effect=crawl), \
                mock.patch('apps.catalog.provider_import.source_fill.wanted_providers', return_value=(['myf2m'], '')):
            stats = airing.hunt(budget_seconds=60)
        entry.refresh_from_db()
        self.assertEqual(stats['found'], 1)
        self.assertEqual(entry.status, AiringEntry.Status.AVAILABLE)
        self.assertIsNotNone(entry.available_at)
        episode = Episode.objects.get(season__series=self.series, episode_number=2)
        self.assertEqual(episode.title, 'The Long Night')  # stub name replaced by TMDB's
        self.assertEqual(episode.air_date, entry.air_date)

    def test_one_crawl_per_series_and_backoff_when_missing(self):
        aired = TODAY - timedelta(days=1)
        self.entry(2, aired)
        self.entry(3, aired)
        with mock.patch.object(airing, '_crawl', return_value='not_found:x') as crawl, \
                mock.patch('apps.catalog.provider_import.source_fill.wanted_providers', return_value=(['myf2m'], '')):
            airing.hunt(budget_seconds=60)
        self.assertEqual(crawl.call_count, 1)
        for row in AiringEntry.objects.all():
            self.assertEqual(row.status, AiringEntry.Status.WAITING)
            self.assertEqual(row.hunt_attempts, 1)
            self.assertGreater(row.next_hunt_at, timezone.now() + timedelta(minutes=100))

    def test_upcoming_release_is_not_crawled(self):
        self.entry(5, TODAY + timedelta(days=3))
        with mock.patch.object(airing, '_crawl') as crawl, \
                mock.patch('apps.catalog.provider_import.source_fill.wanted_providers', return_value=(['myf2m'], '')):
            airing.hunt(budget_seconds=60)
        crawl.assert_not_called()

    def test_release_another_lane_landed_is_caught_without_a_crawl(self):
        entry = self.entry(2, TODAY - timedelta(days=1))
        self.publish_episode(2, 2)
        with mock.patch.object(airing, '_crawl') as crawl, \
                mock.patch('apps.catalog.provider_import.source_fill.wanted_providers', return_value=(['myf2m'], '')):
            stats = airing.hunt(budget_seconds=60)
        crawl.assert_not_called()
        self.assertEqual(stats['already_there'], 1)
        entry.refresh_from_db()
        self.assertEqual(entry.status, AiringEntry.Status.AVAILABLE)


class WeeklyScheduleTests(_Case):
    def test_schedule_reads_airing_rows_with_their_state(self):
        AiringEntry.objects.create(
            kind='episode', series=self.series, season_number=2, episode_number=3,
            air_date=TODAY + timedelta(days=2), status='upcoming', network='HBO', release_type='standard',
        )
        AiringEntry.objects.create(
            kind='episode', series=self.series, season_number=2, episode_number=4,
            air_date=TODAY + timedelta(days=3), status='dropped',
        )
        episode = self.publish_episode(2, 2)
        Episode.objects.filter(pk=episode.pk).update(air_date=TODAY - timedelta(days=4))
        payload = build_weekly_schedule(start=TODAY - timedelta(days=7), days=14)
        self.assertEqual(payload['today'], TODAY.isoformat())
        entries = [row for day in payload['days'] for row in day['entries']]
        self.assertEqual(len(entries), 2)  # the dropped one is gone, the published fallback stays
        upcoming = next(row for row in entries if row['episode_number'] == 3)
        self.assertEqual(upcoming['status'], 'upcoming')
        self.assertEqual(upcoming['network'], 'HBO')
        self.assertFalse(upcoming['available'])
        aired = next(row for row in entries if row['episode_number'] == 2)
        self.assertTrue(aired['available'])
        self.assertNotIn('_popularity', aired)

    def test_due_today_reads_as_waiting(self):
        AiringEntry.objects.create(
            kind='episode', series=self.series, season_number=2, episode_number=3, air_date=TODAY, status='upcoming',
        )
        payload = build_weekly_schedule(start=TODAY - timedelta(days=7), days=14)
        today = next(day for day in payload['days'] if day['is_today'])
        self.assertEqual(today['entries'][0]['status'], 'waiting')


class AvailableScheduleTests(_Case):
    """The public schedule lists only what a viewer can play or download now."""

    def watchable(self, season_number, episode_number, aired):
        episode = self.publish_episode(season_number, episode_number)
        Episode.objects.filter(pk=episode.pk).update(video_url=f'https://cdn.example/s{season_number}e{episode_number}.mp4')
        AiringEntry.objects.create(
            kind='episode', series=self.series, season_number=season_number,
            episode_number=episode_number, air_date=aired, status='available',
        )

    def build(self):
        return build_weekly_schedule(start=TODAY - timedelta(days=6), days=7, available_only=True)

    def test_only_watchable_releases_are_listed(self):
        self.watchable(2, 2, TODAY - timedelta(days=2))
        # Aired but not on the site yet, not aired, and a stale "available" with no episode.
        AiringEntry.objects.create(kind='episode', series=self.series, season_number=2, episode_number=3, air_date=TODAY, status='waiting')
        AiringEntry.objects.create(kind='episode', series=self.series, season_number=2, episode_number=5, air_date=TODAY - timedelta(days=1), status='available')
        # Published but no media at all.
        bare = self.publish_episode(2, 6)
        Episode.objects.filter(pk=bare.pk).update(air_date=TODAY - timedelta(days=1))
        payload = self.build()
        entries = [row for day in payload['days'] for row in day['entries']]
        self.assertEqual([row['episode_number'] for row in entries], [2])
        self.assertTrue(entries[0]['available'])
        self.assertEqual(payload['total'], 1)

    def test_window_never_runs_past_today(self):
        payload = build_weekly_schedule(start=TODAY - timedelta(days=2), days=7, available_only=True)
        self.assertEqual(payload['days'][-1]['date'], TODAY.isoformat())
        self.assertEqual(len(payload['days']), 3)

    def test_same_day_episodes_share_one_card(self):
        aired = TODAY - timedelta(days=1)
        for number in (1, 2, 3):
            self.watchable(3, number, aired)
        day = next(day for day in self.build()['days'] if day['date'] == aired.isoformat())
        self.assertEqual(day['count'], 1)
        card = day['entries'][0]
        self.assertEqual(card['episode_numbers'], [1, 2, 3])
        self.assertEqual(card['episode_number'], 1)
        self.assertIsNone(card['episode_title'])

    def test_unpublished_or_linkless_movie_is_hidden(self):
        movie = Movie.objects.create(
            title='فیلم', original_title='Film', slug='film-2025', tmdb_id=900, is_published=True,
        )
        AiringEntry.objects.create(kind='movie', movie=movie, air_date=TODAY - timedelta(days=1), status='available')
        self.assertEqual(self.build()['total'], 0)
        Movie.objects.filter(pk=movie.pk).update(download_links=[{'url': 'https://cdn.example/film.1080p.mp4', 'quality': '1080p'}])
        self.assertEqual(self.build()['total'], 1)
