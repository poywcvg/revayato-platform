"""«سلامت محتوا»: a rebuild also repairs what put the title on the list, and says so."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from . import title_completion
from .models import ContentIssueReport, Movie, PlaybackSourceGap, PlaybackSubtitleGap
from .playback_sources import DRAFT_GAP_REASON
from .title_problems import fix_problems, open_problems, summary

LINK = {'url': 'https://dl.example/film.2026.1080p.mp4', 'quality': '1080p'}
MKV = {'url': 'https://dl.example/film.2026.1080p.x265.mkv', 'quality': '1080p'}


def _no_blockers():
    return mock.patch('apps.catalog.completeness.publish_blockers', return_value=[])


class _Base(TestCase):
    def setUp(self):
        cache.clear()

    def movie(self, links=(), **extra):
        fields = {
            'title': 'فیلم', 'original_title': 'Film', 'slug': f'film-{Movie.objects.count()}',
            'tmdb_id': 900 + Movie.objects.count(), 'download_links': list(links),
        }
        fields.update(extra)
        return Movie.objects.create(**fields)


class OpenProblemsTests(_Base):
    def test_reads_every_queue_the_health_page_shows(self):
        movie = self.movie([MKV], imdb_id='tt0111161', imdb_rating=7.1, imdb_rating_source='tmdb')
        PlaybackSourceGap.objects.create(content_type='movie', object_id=movie.pk, reason='hevc_only')
        PlaybackSubtitleGap.objects.create(content_type='movie', object_id=movie.pk)
        ContentIssueReport.objects.create(content_type='movie', object_id=movie.pk, problem_type='playback')
        with _no_blockers():
            problems = open_problems(movie)
        self.assertEqual(list(problems), ['source_gap', 'approx_rating', 'subtitle_gap', 'reports'])

    def test_a_clean_title_has_nothing(self):
        movie = self.movie([LINK], imdb_id='tt0111161', imdb_rating=9.3, imdb_rating_source='imdb')
        with _no_blockers():
            self.assertEqual(open_problems(movie), {})

    def test_draft_gap_is_sourceless_not_playback(self):
        movie = self.movie()
        PlaybackSourceGap.objects.create(content_type='movie', object_id=movie.pk, reason=DRAFT_GAP_REASON)
        with _no_blockers():
            self.assertIn('sourceless', open_problems(movie))


class FixProblemsTests(_Base):
    def test_approx_score_is_replaced_by_imdbs_own(self):
        movie = self.movie([LINK], imdb_id='tt0111161', imdb_rating=7.1, imdb_rating_source='tmdb')
        exact = mock.Mock(rating=9.31, votes=3_000_000)
        with _no_blockers(), mock.patch('apps.catalog.imdb_dataset.lookup', return_value=exact):
            result = fix_problems(movie, open_problems(movie))
        movie.refresh_from_db()
        self.assertEqual(result['fixed'], ['approx_rating'])
        self.assertEqual(float(movie.imdb_rating), 9.3)
        self.assertEqual(movie.imdb_rating_source, 'imdb')

    def test_a_score_someone_typed_is_left_alone(self):
        movie = self.movie(
            [LINK], imdb_id='tt0111161', imdb_rating=5.0, imdb_rating_source='tmdb',
            manual_override_fields=['imdb_rating'],
        )
        with _no_blockers(), mock.patch('apps.catalog.imdb_dataset.lookup') as lookup:
            result = fix_problems(movie, {'approx_rating': {}})
        lookup.assert_not_called()
        self.assertEqual(result['actions']['approx_rating'], 'manual')
        movie.refresh_from_db()
        self.assertEqual(float(movie.imdb_rating), 5.0)

    def test_links_found_by_the_rebuild_close_the_sourceless_gap(self):
        movie = self.movie([LINK])
        PlaybackSourceGap.objects.create(content_type='movie', object_id=movie.pk, reason=DRAFT_GAP_REASON)
        with _no_blockers():
            result = fix_problems(movie, open_problems(movie))
        self.assertEqual(result['fixed'], ['sourceless'])
        self.assertFalse(
            PlaybackSourceGap.objects.exclude(status=PlaybackSourceGap.Status.RESOLVED).exists(),
        )

    def test_unplayable_title_is_recrawled_for_a_browser_safe_mirror(self):
        movie = self.movie([MKV])
        PlaybackSourceGap.objects.create(content_type='movie', object_id=movie.pk, reason='hevc_only')

        def heal(obj):
            obj.download_links = [LINK]
            obj.save(update_fields=['download_links'])
            return {'myf2m': ('ok', 1)}

        with _no_blockers(), mock.patch('apps.catalog.playback_sources._recrawl_all_providers', side_effect=heal):
            result = fix_problems(movie, open_problems(movie))
        self.assertEqual(result['actions']['source_gap'], 'refreshed')
        self.assertEqual(result['fixed'], ['source_gap'])

    def test_a_rebuild_that_just_crawled_does_not_crawl_again(self):
        movie = self.movie([MKV])
        PlaybackSourceGap.objects.create(content_type='movie', object_id=movie.pk, reason='hevc_only')
        with _no_blockers(), mock.patch('apps.catalog.playback_sources._recrawl_all_providers') as crawl:
            result = fix_problems(movie, open_problems(movie), recrawled=True)
        crawl.assert_not_called()
        self.assertEqual(result['actions']['source_gap'], 'unavailable')

    def test_subtitles_left_to_the_callers_forced_hunt_count_as_queued(self):
        movie = self.movie([LINK], is_published=True)
        PlaybackSubtitleGap.objects.create(content_type='movie', object_id=movie.pk)
        with (
            _no_blockers(),
            mock.patch('apps.catalog.tasks.enqueue_movie_softsub_urgent') as hunt,
        ):
            result = fix_problems(movie, open_problems(movie), verified=True, queue_subtitles=False)
        hunt.assert_not_called()
        self.assertEqual(result['queued'], ['subtitle_gap'])

    def test_a_staged_rebuild_never_recrawls_links_behind_its_test(self):
        movie = self.movie([MKV])
        PlaybackSourceGap.objects.create(content_type='movie', object_id=movie.pk, reason='hevc_only')
        with _no_blockers(), mock.patch('apps.catalog.playback_sources._recrawl_all_providers') as crawl:
            result = fix_problems(movie, open_problems(movie), touch_links=False)
        crawl.assert_not_called()
        self.assertEqual(result['left'], ['source_gap'])

    def test_subtitle_gap_gets_a_forced_hunt_and_counts_as_queued(self):
        movie = self.movie([LINK], is_published=True)
        PlaybackSubtitleGap.objects.create(content_type='movie', object_id=movie.pk)
        with (
            _no_blockers(),
            mock.patch('apps.catalog.tasks.enqueue_movie_softsub_urgent') as hunt,
            mock.patch('apps.catalog.media_verification.verify_target', return_value={'status': 'passed'}),
        ):
            result = fix_problems(movie, open_problems(movie), verified=True)
        hunt.assert_called_once_with(movie.pk, force=True)
        self.assertIn('subtitle_gap', result['queued'])
        self.assertNotIn('subtitle_gap', result['left'])

    def test_summary_names_each_problem(self):
        line = summary({'fixed': ['approx_rating'], 'queued': ['subtitle_gap'], 'left': ['reports']})
        self.assertEqual(line, 'رفع شد: نمرهٔ تقریبی · در صف: زیرنویس · باقی مانده: گزارش کاربر')


class PipelineTests(_Base):
    def test_rebuild_runs_the_problem_step_and_records_the_outcome(self):
        movie = self.movie([LINK], imdb_id='tt0111161', imdb_rating=7.1, imdb_rating_source='tmdb')
        patches = {
            'apps.catalog.admin_ops._resync_tmdb': mock.Mock(return_value={'synced': True}),
            'apps.catalog.title_repair.repair_titles': mock.Mock(return_value={'changed': {}}),
            'apps.catalog.provider_import.source_fill.wanted_providers': mock.Mock(return_value=([], '')),
            'apps.catalog.link_sizes.size_title': mock.Mock(return_value={'sized': 0, 'left': 0}),
            'apps.catalog.media_verification.verify_target': mock.Mock(return_value={'status': 'passed'}),
            'apps.catalog.completeness.publish_blockers': mock.Mock(return_value=[]),
            'apps.catalog.media_verification.media_publish_blockers': mock.Mock(return_value=[]),
            'apps.catalog.tasks.enqueue_movie_softsub_urgent': mock.Mock(return_value=True),
            'apps.catalog.playback_gate.gate_links': mock.Mock(return_value=(mock.Mock(), [])),
            'apps.catalog.imdb_dataset.lookup': mock.Mock(return_value=mock.Mock(rating=8.4, votes=10)),
        }
        started = [mock.patch(target, new) for target, new in patches.items()]
        for patcher in started:
            patcher.start()
        try:
            state = title_completion.run_completion('movie', movie.pk, publish=False, mode='rebuild')
        finally:
            for patcher in started:
                patcher.stop()
        steps = {row['key']: row for row in state['steps']}
        self.assertEqual(steps['problems']['status'], 'ok')
        self.assertEqual(steps['problems']['fixed'], ['approx_rating'])
        self.assertEqual(state['problems_fixed'], ['approx_rating'])
        self.assertEqual(state['problems_left'], [])
