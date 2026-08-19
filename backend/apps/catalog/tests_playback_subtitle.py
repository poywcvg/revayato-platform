from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.catalog.models import Movie, PlaybackSubtitleGap
from apps.catalog.playback_subtitle import read_playback_subtitle_status


@override_settings(
    SUBTITLESTAR_ENABLED=True,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class PlaybackSubtitleEnsureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.movie = Movie.objects.create(
            title='Ensure SoftSub',
            original_title='Ensure SoftSub',
            slug='ensure-softsub-test',
            imdb_id='tt0111161',
            is_published=True,
            download_links=[{
                'url': 'https://cdn.example/movie.Dub.1080p.mkv',
                'label': 'دوبله فارسی · WEB-DL 1080p',
                'quality': '1080p',
            }],
            subtitle_tracks=[],
        )

    def test_ensure_reports_and_queues(self):
        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent', return_value=True),
            patch('apps.catalog.subtitle_extract._attach_subtitlestar_subtitle', return_value=False),
            patch('apps.catalog.subtitle_extract._attach_subzone_subtitle', return_value=False),
        ):
            response = self.client.post(
                '/api/catalog/playback-subtitle-ensure/',
                {
                    'content_type': 'movie',
                    'slug': self.movie.slug,
                    'version': 'dub',
                    'sync': True,
                },
                format='json',
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('reported'))
        gap = PlaybackSubtitleGap.objects.get(content_type='movie', object_id=self.movie.pk)
        self.assertEqual(gap.report_count, 1)
        self.assertIn(gap.status, {
            PlaybackSubtitleGap.Status.QUEUED,
            PlaybackSubtitleGap.Status.OPEN,
            PlaybackSubtitleGap.Status.UNAVAILABLE,
            PlaybackSubtitleGap.Status.RESOLVED,
        })
        self.assertIn(response.data.get('status'), {'queued', 'unavailable', 'ready', 'burned_in'})

    def test_ensure_ready_when_tracks_exist(self):
        self.movie.subtitle_tracks = [{
            'id': 'fa-1',
            'language': 'fa',
            'label': 'فارسی',
            'key': 'catalog/subtitles/test.vtt',
        }]
        self.movie.save(update_fields=['subtitle_tracks'])
        response = self.client.post(
            '/api/catalog/playback-subtitle-ensure/',
            {'content_type': 'movie', 'slug': self.movie.slug, 'sync': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'ready')
        self.assertFalse(response.data.get('reported'))

    def test_background_import_resolves_open_report(self):
        gap = PlaybackSubtitleGap.objects.create(
            content_type='movie',
            object_id=self.movie.pk,
            episode_id=0,
            slug=self.movie.slug,
            title=self.movie.title,
            status=PlaybackSubtitleGap.Status.QUEUED,
        )
        from apps.catalog.playback_subtitle import resolve_playback_subtitle_gaps

        updated = resolve_playback_subtitle_gaps(
            content_type='movie',
            object_id=self.movie.pk,
            last_result='softsub-ffmpeg',
        )
        gap.refresh_from_db()
        self.assertEqual(updated, 1)
        self.assertEqual(gap.status, PlaybackSubtitleGap.Status.RESOLVED)
        self.assertEqual(gap.last_result, 'softsub-ffmpeg')
        self.assertIsNotNone(gap.resolved_at)

    @override_settings(SOFTSUB_ALLOW_FFMPEG=True, SUBTITLESTAR_ENABLED=True, SUBZONE_ENABLED=True)
    def test_ensure_queues_ffmpeg_worker_when_providers_miss(self):
        """A soft-only report queues exact-source extraction AND still syncs providers."""
        self.movie.download_links = [{
            'url': 'https://cdn.example/Soft/movie.Soft.480p.mkv',
            'label': 'زیرنویس فارسی · Soft 480p',
            'quality': '480p',
            'kind': 'softsub',
        }]
        self.movie.save(update_fields=['download_links'])

        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent', return_value=True) as enqueue,
            patch('apps.catalog.subtitle_extract._attach_subtitlestar_subtitle', return_value=False) as star,
            patch('apps.catalog.subtitle_extract._attach_subzone_subtitle', return_value=False) as subzone,
            patch('apps.catalog.subtitle_extract.extract_webvtt_from_url') as extract,
        ):
            from apps.catalog.playback_subtitle import ensure_playback_subtitles
            result = ensure_playback_subtitles(
                content_type='movie',
                slug=self.movie.slug,
                playback_source_url='https://cdn.example/Soft/movie.Soft.480p.mkv',
                sync=True,
                timeout_seconds=20,
            )

        self.movie.refresh_from_db()
        self.assertEqual(result.get('status'), 'queued')
        self.assertTrue(result.get('queued'))
        self.assertFalse(self.movie.subtitle_tracks)
        enqueue.assert_called_once()
        self.assertEqual(
            enqueue.call_args.kwargs.get('preferred_source_url'),
            'https://cdn.example/Soft/movie.Soft.480p.mkv',
        )
        # ffmpeg stays on the worker; the player request only does provider lookups.
        extract.assert_not_called()
        star.assert_called_once()
        subzone.assert_called_once()
        self.assertEqual(result.get('message'), 'extracting_embedded')

    @override_settings(SOFTSUB_ALLOW_FFMPEG=True, SUBTITLESTAR_ENABLED=True, SUBZONE_ENABLED=True)
    def test_ensure_sync_attaches_star_when_soft_queued(self):
        """A soft-only movie gets provider sidecars in the sync lane immediately."""
        self.movie.download_links = [{
            'url': 'https://cdn.example/Soft/movie.Soft.480p.mkv',
            'label': 'زیرنویس فارسی · Soft 480p',
            'quality': '480p',
            'kind': 'softsub',
        }]
        self.movie.save(update_fields=['download_links'])

        def _fake_star(movie, links, *, timeout_seconds):
            movie.subtitle_tracks = [{
                'id': 'fa-subtitlestar-1',
                'language': 'fa',
                'label': 'فارسی',
                'key': 'catalog/subtitles/star-test.vtt',
                'provider': 'subtitlestar',
            }]
            movie.has_subtitle = True
            movie.save(update_fields=['subtitle_tracks', 'has_subtitle'])
            return True

        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent', return_value=True),
            patch('apps.catalog.subtitle_extract._attach_subtitlestar_subtitle', side_effect=_fake_star),
        ):
            from apps.catalog.playback_subtitle import ensure_playback_subtitles
            result = ensure_playback_subtitles(
                content_type='movie',
                slug=self.movie.slug,
                sync=True,
                timeout_seconds=14,
            )

        self.movie.refresh_from_db()
        self.assertEqual(result.get('status'), 'ready')
        self.assertTrue(result.get('has_subtitle_tracks'))
        self.assertTrue(result.get('synced'))
        self.assertEqual(self.movie.subtitle_tracks[0].get('provider'), 'subtitlestar')

    @override_settings(SUBTITLESTAR_ENABLED=True, SUBZONE_ENABLED=True)
    def test_ensure_attaches_subzone_when_star_misses(self):
        self.movie.download_links = [{
            'url': 'https://cdn.example/Original/movie.WEB-DL.720p.mkv',
            'label': 'نسخه اصلی · WEB-DL 720p',
            'quality': '720p',
            'kind': 'video',
        }]
        self.movie.save(update_fields=['download_links'])

        def _fake_subzone(movie, links, *, timeout_seconds):
            movie.subtitle_tracks = [{
                'id': 'fa-subzone-1',
                'language': 'fa',
                'label': 'فارسی',
                'key': 'catalog/subtitles/subzone-test.vtt',
                'provider': 'subzone',
            }]
            movie.has_subtitle = True
            movie.save(update_fields=['subtitle_tracks', 'has_subtitle'])
            return True

        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent', return_value=True),
            patch('apps.catalog.subtitle_extract._attach_subtitlestar_subtitle', return_value=False),
            patch('apps.catalog.subtitle_extract._attach_subzone_subtitle', side_effect=_fake_subzone),
        ):
            from apps.catalog.playback_subtitle import ensure_playback_subtitles
            result = ensure_playback_subtitles(
                content_type='movie',
                slug=self.movie.slug,
                sync=True,
                timeout_seconds=14,
            )

        self.movie.refresh_from_db()
        self.assertEqual(result.get('status'), 'ready')
        self.assertTrue(result.get('has_subtitle_tracks'))
        self.assertTrue(self.movie.subtitle_tracks)
        self.assertEqual(self.movie.subtitle_tracks[0].get('provider'), 'subzone')

    def test_ensure_reports_burned_in_for_hardsub_only(self):
        self.movie.download_links = [{
            'url': 'https://cdn.example/Hard/movie.HardSub.1080p.mkv',
            'label': 'زیرنویس چسبیده · 1080p',
            'quality': '1080p',
            'kind': 'hardsub',
            'subtitle_type': 'hard',
        }]
        self.movie.save(update_fields=['download_links'])

        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent', return_value=True) as enqueue,
            patch('apps.catalog.subtitle_extract._attach_subtitlestar_subtitle', return_value=False),
            patch('apps.catalog.subtitle_extract._attach_subzone_subtitle', return_value=False),
        ):
            from apps.catalog.playback_subtitle import ensure_playback_subtitles
            result = ensure_playback_subtitles(
                content_type='movie',
                slug=self.movie.slug,
                playback_version='hardsub',
                sync=True,
                timeout_seconds=10,
            )

        # HardSub-only still reports + queues sidecars; cues may land async.
        self.assertTrue(result.get('reported'))
        self.assertTrue(result.get('queued'))
        enqueue.assert_called_once()
        self.assertIn(result.get('status'), {'queued', 'burned_in'})
        self.assertIn(result.get('message'), {'loading', 'hardsub_burned_in', 'burned_in_queued'})


@override_settings(
    SUBTITLESTAR_ENABLED=True,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class PlaybackSubtitleStatusTests(TestCase):
    """The lightweight GET poll: reads persisted state, never touches providers."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.movie = Movie.objects.create(
            title='Status Movie',
            original_title='Status Movie',
            slug='status-movie-test',
            imdb_id='tt0111161',
            is_published=True,
            download_links=[{
                'url': 'https://cdn.example/Original/movie.720p.mkv',
                'label': 'نسخه اصلی · 720p',
                'quality': '720p',
            }],
            subtitle_tracks=[],
        )

    def test_status_reports_ready_with_tracks_when_persisted(self):
        gap = PlaybackSubtitleGap.objects.create(
            content_type='movie',
            object_id=self.movie.pk,
            episode_id=0,
            slug=self.movie.slug,
            title=self.movie.title,
            status=PlaybackSubtitleGap.Status.OPEN,
        )
        self.movie.subtitle_tracks = [{
            'id': 'fa-1',
            'language': 'fa',
            'label': 'فارسی',
            'key': 'catalog/subtitles/persisted.vtt',
        }]
        self.movie.save(update_fields=['subtitle_tracks'])

        response = self.client.get(
            '/api/catalog/playback-subtitle-status/',
            {'report_id': gap.pk, 'content_type': 'movie', 'slug': self.movie.slug},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'ready')
        self.assertTrue(response.data.get('has_subtitle_tracks'))
        self.assertEqual(response.data.get('report_id'), gap.pk)
        self.assertTrue(response.data.get('reported'))
        self.assertEqual(response.data['subtitle_tracks'][0]['key'], 'catalog/subtitles/persisted.vtt')
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_status_never_enqueues(self):
        gap = PlaybackSubtitleGap.objects.create(
            content_type='movie',
            object_id=self.movie.pk,
            episode_id=0,
            slug=self.movie.slug,
            title=self.movie.title,
            status=PlaybackSubtitleGap.Status.QUEUED,
        )
        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent') as enqueue_movie,
            patch('apps.catalog.tasks.enqueue_series_softsub_urgent') as enqueue_series,
        ):
            response = self.client.get(
                '/api/catalog/playback-subtitle-status/',
                {'report_id': gap.pk, 'content_type': 'movie', 'slug': self.movie.slug},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'queued')
        self.assertFalse(response.data.get('has_subtitle_tracks'))
        enqueue_movie.assert_not_called()
        enqueue_series.assert_not_called()

    def test_status_missing_report(self):
        response = self.client.get(
            '/api/catalog/playback-subtitle-status/',
            {'report_id': 999999, 'content_type': 'movie', 'slug': self.movie.slug},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'missing_report')
        self.assertEqual(response.data.get('message'), 'report_not_found')
        self.assertFalse(response.data.get('has_subtitle_tracks'))

    def test_status_invalid(self):
        response = self.client.get(
            '/api/catalog/playback-subtitle-status/',
            {'report_id': 1, 'content_type': 'film', 'slug': self.movie.slug},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'invalid')
        self.assertEqual(response.data.get('message'), 'invalid_request')

    def test_status_queued_when_open(self):
        gap = PlaybackSubtitleGap.objects.create(
            content_type='movie',
            object_id=self.movie.pk,
            episode_id=0,
            slug=self.movie.slug,
            title=self.movie.title,
            status=PlaybackSubtitleGap.Status.OPEN,
        )
        response = self.client.get(
            '/api/catalog/playback-subtitle-status/',
            {'content_type': 'movie', 'slug': self.movie.slug},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'queued')
        self.assertFalse(response.data.get('has_subtitle_tracks'))
        # No report_id given → resolved by identity; report_id still surfaced.
        self.assertEqual(response.data.get('report_id'), gap.pk)

    def test_status_missing_title(self):
        response = self.client.get(
            '/api/catalog/playback-subtitle-status/',
            {'content_type': 'movie', 'slug': 'no-such-movie'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('status'), 'missing')
        self.assertEqual(response.data.get('message'), 'title_not_found')


@override_settings(
    SUBTITLESTAR_ENABLED=True,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class PlaybackSubtitleStampedeTests(TestCase):
    """Repeated reports of the same open gap must NOT clear circuits or miss caches."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.movie = Movie.objects.create(
            title='Stampede Movie',
            original_title='Stampede Movie',
            slug='stampede-movie-test',
            imdb_id='tt0111161',
            is_published=True,
            download_links=[{
                'url': 'https://cdn.example/Original/movie.720p.mkv',
                'label': 'نسخه اصلی · 720p',
                'quality': '720p',
            }],
            subtitle_tracks=[],
        )

    def test_stampede_keeps_circuits_closed(self):
        """A repeat viewer report preserves the provider circuit-open flag."""
        gap = PlaybackSubtitleGap.objects.create(
            content_type='movie',
            object_id=self.movie.pk,
            episode_id=0,
            slug=self.movie.slug,
            title=self.movie.title,
            status=PlaybackSubtitleGap.Status.OPEN,
        )
        # Same gap already reported once → this is a repeat viewer, not a fresh report.
        PlaybackSubtitleGap.objects.filter(pk=gap.pk).update(report_count=2)

        for provider_key in ('catalog:subtitlestar:circuit-open', 'catalog:subzone:circuit-open'):
            cache.set(provider_key, True, timeout=1800)
        for miss_key in ('catalog:subtitlestar:miss:tt0111161', 'catalog:subzone:miss:tt0111161'):
            cache.set(miss_key, True, timeout=86400)

        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent', return_value=True),
            patch('apps.catalog.subtitle_extract._attach_subtitlestar_subtitle', return_value=False),
            patch('apps.catalog.subtitle_extract._attach_subzone_subtitle', return_value=False),
        ):
            for _ in range(2):
                response = self.client.post(
                    '/api/catalog/playback-subtitle-ensure/',
                    {'content_type': 'movie', 'slug': self.movie.slug, 'sync': False},
                    format='json',
                )
                self.assertEqual(response.status_code, 200)

        # Both circuits must remain closed; miss caches must stay cached.
        self.assertTrue(cache.get('catalog:subtitlestar:circuit-open'))
        self.assertTrue(cache.get('catalog:subzone:circuit-open'))
        self.assertTrue(cache.get('catalog:subtitlestar:miss:tt0111161'))
        self.assertTrue(cache.get('catalog:subzone:miss:tt0111161'))
        gap.refresh_from_db()
        self.assertEqual(gap.report_count, 4)

    def test_fresh_report_clears_miss_caches_but_not_circuits(self):
        """A genuinely-new report gets one re-probe, but circuits stay closed."""
        for provider_key in ('catalog:subtitlestar:circuit-open', 'catalog:subzone:circuit-open'):
            cache.set(provider_key, True, timeout=1800)
        for miss_key in ('catalog:subtitlestar:miss:tt0111161', 'catalog:subzone:miss:tt0111161'):
            cache.set(miss_key, True, timeout=86400)

        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent', return_value=True),
            patch('apps.catalog.subtitle_extract._attach_subtitlestar_subtitle', return_value=False),
            patch('apps.catalog.subtitle_extract._attach_subzone_subtitle', return_value=False),
        ):
            response = self.client.post(
                '/api/catalog/playback-subtitle-ensure/',
                {'content_type': 'movie', 'slug': self.movie.slug, 'sync': False},
                format='json',
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data.get('reported'))

        # Fresh report clears stale misses so providers get one re-probe…
        self.assertIsNone(cache.get('catalog:subtitlestar:miss:tt0111161'))
        self.assertIsNone(cache.get('catalog:subzone:miss:tt0111161'))
        # …but the genuinely-down provider stays closed.
        self.assertTrue(cache.get('catalog:subtitlestar:circuit-open'))
        self.assertTrue(cache.get('catalog:subzone:circuit-open'))


@override_settings(
    SUBTITLESTAR_ENABLED=True,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class PlaybackSubtitleStatusReaderTests(TestCase):
    """Direct unit coverage of read_playback_subtitle_status (bypasses the view)."""

    def setUp(self):
        cache.clear()
        self.movie = Movie.objects.create(
            title='Reader Movie',
            original_title='Reader Movie',
            slug='reader-movie-test',
            imdb_id='tt0111161',
            is_published=True,
            download_links=[{
                'url': 'https://cdn.example/Original/movie.720p.mkv',
                'label': 'نسخه اصلی · 720p',
                'quality': '720p',
            }],
            subtitle_tracks=[],
        )

    def test_reader_rejects_unknown_kind(self):
        result = read_playback_subtitle_status(
            content_type='audio', slug=self.movie.slug,
        )
        self.assertEqual(result['status'], 'invalid')

    def test_reader_uses_episode_tracks_for_series(self):
        gap = PlaybackSubtitleGap.objects.create(
            content_type='series',
            object_id=4242,
            episode_id=7,
            slug='reader-series-test',
            title='Reader Series',
            status=PlaybackSubtitleGap.Status.QUEUED,
        )
        result = read_playback_subtitle_status(
            report_id=gap.pk,
            content_type='series',
            slug='reader-series-test',
            episode_id=7,
        )
        self.assertEqual(result['status'], 'missing')  # no such series → missing title
        self.assertFalse(result['has_subtitle_tracks'])

    def test_reader_never_enqueues(self):
        gap = PlaybackSubtitleGap.objects.create(
            content_type='movie',
            object_id=self.movie.pk,
            episode_id=0,
            slug=self.movie.slug,
            title=self.movie.title,
            status=PlaybackSubtitleGap.Status.OPEN,
        )
        with (
            patch('apps.catalog.tasks.enqueue_movie_softsub_urgent') as enqueue_movie,
            patch('apps.catalog.tasks.enqueue_series_softsub_urgent') as enqueue_series,
        ):
            result = read_playback_subtitle_status(
                report_id=gap.pk,
                content_type='movie',
                slug=self.movie.slug,
            )
        self.assertEqual(result['status'], 'queued')
        self.assertFalse(result['has_subtitle_tracks'])
        self.assertEqual(result['report_id'], gap.pk)
        enqueue_movie.assert_not_called()
        enqueue_series.assert_not_called()
