from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.catalog.models import Movie, PlaybackSubtitleGap


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
