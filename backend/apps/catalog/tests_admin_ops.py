"""The operations desk: what staff can see, what they can change, what they cannot.

The point of most of these is the *boundary*, not the happy path. An admin panel
that can rewrite a live catalog is only safe if "delete" archives, if a link can
only be added through the same identity guard the importer uses, and if one
show's episode id cannot be used to write a verdict onto another show.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import (
    ContentIssueReport, Episode, MediaCheck, Movie, MovieSyncAudit,
    PlaybackSourceGap, Season, Series,
)

User = get_user_model()

ABR = 'https://cdn.abrtech.top/yA3f/Film/2019/Joker.2019/Joker.2019.1080p.BluRay.x264.mp4'
OTHER_FILM = 'https://cdn.abrtech.top/yA3f/Film/2014/Interstellar.2014/Interstellar.2014.1080p.BluRay.x264.mp4'


class OpsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username='ops-staff', email='ops@example.com', password='x', is_staff=True,
        )
        self.viewer = User.objects.create_user(
            username='ops-viewer', email='viewer@example.com', password='x',
        )
        self.movie = Movie.objects.create(
            title='جوکر', original_title='Joker', slug='joker-ops',
            release_year=2019, imdb_rating=8.4,
            download_links=[{'url': ABR, 'quality': '1080p', 'label': '۱۰۸۰'}],
        )

    def desk_url(self, kind='movie', object_id=None):
        return reverse('admin_media_desk', args=[kind, object_id or self.movie.pk])

    def as_staff(self):
        # The admin API authenticates by JWT only — a Django session login is
        # invisible to it and answers 401.
        self.client.force_authenticate(self.staff)


class MediaDeskReadTests(OpsTestCase):
    def test_staff_only(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.desk_url()).status_code, 403)

    def test_anonymous_is_refused(self):
        self.assertIn(self.client.get(self.desk_url()).status_code, (401, 403))

    def test_an_unknown_kind_is_a_bad_request_not_a_crash(self):
        self.as_staff()
        response = self.client.get(self.desk_url(kind='album', object_id=1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'unknown_kind')

    def test_the_desk_reports_links_gaps_and_blockers_in_one_payload(self):
        self.as_staff()
        PlaybackSourceGap.objects.create(
            content_type='movie', object_id=self.movie.pk, slug=self.movie.slug,
            title=self.movie.title, reason='hevc_only',
        )
        ContentIssueReport.objects.create(
            content_type='movie', object_id=self.movie.pk, slug=self.movie.slug,
            problem_type=ContentIssueReport.Problem.PLAYBACK,
        )
        body = self.client.get(self.desk_url()).json()
        self.assertEqual(body['kind'], 'movie')
        self.assertEqual(len(body['links']), 1)
        self.assertEqual(body['links'][0]['url'], ABR)
        # Nobody has probed it, so the desk must say so rather than imply health.
        self.assertEqual(body['links'][0]['health'], 'unchecked')
        self.assertEqual(body['source_gap']['reason'], 'hevc_only')
        self.assertEqual(len(body['reports']), 1)
        self.assertIn('publish_blockers', body)
        self.assertIn('diagnosis', body)

    def test_a_stored_probe_verdict_reaches_the_link_row(self):
        self.as_staff()
        MediaCheck.objects.create(
            content_type='movie', object_id=self.movie.pk,
            status=MediaCheck.Status.FAILED, reason='all_sources_dead',
            checked_urls=1, dead_urls=1, checked_at=timezone.now(),
            detail={'probes': [{'url': ABR, 'verdict': 'dead', 'reason': 'http_404', 'safe': True}]},
        )
        row = self.client.get(self.desk_url()).json()['links'][0]
        self.assertEqual(row['health'], 'dead')
        self.assertEqual(row['reason'], 'http_404')


class LinkControlTests(OpsTestCase):
    def test_removing_a_link_leaves_the_row_and_writes_an_audit(self):
        self.as_staff()
        response = self.client.post(
            self.desk_url(), {'action': 'remove_link', 'url': ABR},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.download_links, [])
        self.assertTrue(Movie.objects.filter(pk=self.movie.pk).exists())
        audit = MovieSyncAudit.objects.filter(movie=self.movie).first()
        self.assertEqual(audit.details['reason'], 'remove_link')

    def test_a_link_belonging_to_another_film_is_refused(self):
        self.as_staff()
        response = self.client.post(
            self.desk_url(), {'action': 'add_link', 'url': OTHER_FILM},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'contaminated_link')
        self.movie.refresh_from_db()
        self.assertEqual(len(self.movie.download_links), 1)

    def test_an_admin_can_override_the_identity_guard_on_purpose(self):
        self.as_staff()
        response = self.client.post(
            self.desk_url(), {'action': 'add_link', 'url': OTHER_FILM, 'force': True},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.movie.refresh_from_db()
        self.assertEqual(len(self.movie.download_links), 2)

    def test_a_matching_link_is_accepted_without_force(self):
        self.as_staff()
        extra = ABR.replace('1080p', '720p')
        response = self.client.post(
            self.desk_url(), {'action': 'add_link', 'url': extra, 'quality': '720p'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.movie.refresh_from_db()
        self.assertEqual(len(self.movie.download_links), 2)

    def test_pruning_only_removes_links_a_host_reported_gone(self):
        self.as_staff()
        alive = ABR.replace('1080p', '720p')
        self.movie.download_links = [
            {'url': ABR, 'quality': '1080p'}, {'url': alive, 'quality': '720p'},
        ]
        self.movie.save(update_fields=['download_links'])
        MediaCheck.objects.create(
            content_type='movie', object_id=self.movie.pk,
            status=MediaCheck.Status.UNKNOWN, checked_at=timezone.now(),
            detail={'probes': [
                {'url': ABR, 'verdict': 'dead', 'reason': 'http_404'},
                {'url': alive, 'verdict': 'unknown', 'reason': 'timeout'},
            ]},
        )
        response = self.client.post(
            self.desk_url(), {'action': 'prune_dead'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.movie.refresh_from_db()
        # The unknown one stays: doubt is not proof, and dropping it would take a
        # working title offline over one flaky probe.
        self.assertEqual([i['url'] for i in self.movie.download_links], [alive])

    def test_stripping_contamination_uses_the_importers_own_classifier(self):
        self.as_staff()
        self.movie.download_links = [{'url': ABR}, {'url': OTHER_FILM}]
        self.movie.save(update_fields=['download_links'])
        response = self.client.post(
            self.desk_url(), {'action': 'strip_contaminated'}, format='json',
        )
        self.assertEqual(response.json()['result']['removed'], 1)
        self.movie.refresh_from_db()
        self.assertEqual([i['url'] for i in self.movie.download_links], [ABR])

    def test_an_unknown_action_is_named_in_the_error(self):
        self.as_staff()
        response = self.client.post(
            self.desk_url(), {'action': 'drop_database'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'unknown_action')


class PublicationTests(OpsTestCase):
    def test_publishing_refuses_a_title_the_importer_would_refuse(self):
        self.as_staff()
        response = self.client.post(
            self.desk_url(), {'action': 'publish'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'publish_blocked')
        self.movie.refresh_from_db()
        self.assertFalse(self.movie.is_published)

    def test_force_publishes_and_records_what_was_overridden(self):
        self.as_staff()
        response = self.client.post(
            self.desk_url(), {'action': 'publish', 'force': True}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.movie.refresh_from_db()
        self.assertTrue(self.movie.is_published)
        audit = MovieSyncAudit.objects.filter(movie=self.movie).first()
        self.assertTrue(audit.details['forced'])
        self.assertTrue(audit.details['blockers'])

    def test_archiving_keeps_the_row(self):
        self.as_staff()
        self.client.post(self.desk_url(), {'action': 'archive'}, format='json')
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.publication_status, Movie.PublicationStatus.ARCHIVED)
        self.assertFalse(self.movie.is_published)
        self.assertTrue(Movie.objects.filter(pk=self.movie.pk).exists())


class SeriesDeskTests(OpsTestCase):
    def setUp(self):
        super().setUp()
        self.series = Series.objects.create(
            title='برکینگ بد', original_title='Breaking Bad', slug='breaking-bad-ops',
            start_year=2008,
            download_links=[{'url': 'https://cdn.abrtech.top/yA3f/Series/Breaking.Bad/Breaking.Bad.S01E01.1080p.mkv',
                             'season_number': 1, 'episode_number': 1}],
        )
        self.season = Season.objects.create(series=self.series, season_number=1, episode_count=2)
        self.episode = Episode.objects.create(season=self.season, episode_number=1, title='Pilot')
        self.other_series = Series.objects.create(
            title='دیگر', original_title='Other', slug='other-ops', start_year=2010,
        )
        other_season = Season.objects.create(series=self.other_series, season_number=1)
        self.foreign_episode = Episode.objects.create(season=other_season, episode_number=1, title='Nope')

    def test_the_series_desk_lists_episodes_with_their_own_state(self):
        self.as_staff()
        body = self.client.get(self.desk_url('series', self.series.pk)).json()
        self.assertEqual(len(body['episodes']), 1)
        row = body['episodes'][0]
        self.assertEqual(row['season_number'], 1)
        self.assertEqual(row['episode_number'], 1)
        self.assertEqual(row['link_count'], 1)
        self.assertFalse(row['has_stream'])

    def test_an_episode_of_another_series_is_not_accepted(self):
        self.as_staff()
        self.episode.subtitle_tracks = [{'src': 'a.vtt', 'label': 'fa', 'lang': 'fa'}]
        self.episode.save(update_fields=['subtitle_tracks'])
        self.foreign_episode.subtitle_tracks = [{'src': 'b.vtt', 'label': 'fa', 'lang': 'fa'}]
        self.foreign_episode.save(update_fields=['subtitle_tracks'])
        response = self.client.post(
            self.desk_url('series', self.series.pk),
            {'action': 'remove_subtitle', 'episode_id': self.foreign_episode.pk, 'index': 0},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.foreign_episode.refresh_from_db()
        self.assertEqual(len(self.foreign_episode.subtitle_tracks), 1)

    def test_archiving_a_series_now_leaves_an_audit_trail(self):
        self.as_staff()
        self.series.is_published = True
        self.series.save(update_fields=['is_published'])
        response = self.client.delete(reverse('admin_series_detail', args=[self.series.pk]))
        self.assertEqual(response.status_code, 200)
        audit = MovieSyncAudit.objects.filter(action=MovieSyncAudit.Action.ARCHIVE).first()
        self.assertEqual(audit.details['kind'], 'series')
        self.assertEqual(audit.details['object_id'], self.series.pk)
        self.assertTrue(Series.objects.filter(pk=self.series.pk).exists())


class BulkTests(OpsTestCase):
    def setUp(self):
        super().setUp()
        self.second = Movie.objects.create(
            title='دوم', original_title='Second', slug='second-ops',
            release_year=2020, imdb_rating=7.0, is_published=True,
        )

    def test_bulk_archive_applies_to_every_selected_title(self):
        self.as_staff()
        response = self.client.post(
            reverse('admin_catalog_bulk'),
            {'kind': 'movie', 'action': 'archive', 'ids': [self.movie.pk, self.second.pk]},
            format='json',
        )
        body = response.json()
        self.assertEqual(body['succeeded'], 2)
        self.second.refresh_from_db()
        self.assertEqual(self.second.publication_status, Movie.PublicationStatus.ARCHIVED)

    def test_a_missing_id_is_reported_rather_than_failing_the_batch(self):
        self.as_staff()
        body = self.client.post(
            reverse('admin_catalog_bulk'),
            {'kind': 'movie', 'action': 'archive', 'ids': [self.movie.pk, 99999]},
            format='json',
        ).json()
        self.assertEqual(body['succeeded'], 1)
        self.assertEqual(body['failed'], 1)
        self.assertEqual(body['results'][1]['error'], 'not_found')

    def test_a_network_bound_verb_refuses_an_oversized_selection(self):
        self.as_staff()
        response = self.client.post(
            reverse('admin_catalog_bulk'),
            {'kind': 'movie', 'action': 'verify', 'ids': list(range(1, 60))},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'selection_too_large')

    def test_an_action_that_is_not_bulk_safe_is_refused(self):
        self.as_staff()
        response = self.client.post(
            reverse('admin_catalog_bulk'),
            {'kind': 'movie', 'action': 'add_link', 'ids': [self.movie.pk], 'url': ABR},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'unknown_action')


class HealthQueueTests(OpsTestCase):
    def test_counts_come_back_for_every_queue(self):
        self.as_staff()
        PlaybackSourceGap.objects.create(
            content_type='movie', object_id=self.movie.pk, title=self.movie.title, reason='hevc_only',
        )
        body = self.client.get(reverse('admin_catalog_health')).json()
        self.assertEqual(body['counts']['source_gaps'], 1)
        for key in ('subtitle_gaps', 'failed_checks', 'reports', 'unverified', 'incomplete'):
            self.assertIn(key, body['counts'])

    def test_a_gap_row_resolves_to_a_clickable_title(self):
        self.as_staff()
        PlaybackSourceGap.objects.create(
            content_type='movie', object_id=self.movie.pk, title=self.movie.title, reason='hevc_only',
        )
        row = self.client.get(reverse('admin_catalog_health'), {'queue': 'source_gaps'}).json()['results'][0]
        self.assertEqual(row['target']['title'], 'جوکر')
        self.assertEqual(row['target']['slug'], 'joker-ops')

    def test_a_published_title_nobody_probed_shows_up_as_unverified(self):
        self.as_staff()
        self.movie.is_published = True
        self.movie.save(update_fields=['is_published'])
        body = self.client.get(reverse('admin_catalog_health'), {'queue': 'unverified'}).json()
        self.assertEqual([row['target']['id'] for row in body['results']], [self.movie.pk])

    def test_an_unknown_queue_is_refused(self):
        self.as_staff()
        response = self.client.get(reverse('admin_catalog_health'), {'queue': 'nope'})
        self.assertEqual(response.status_code, 400)


class OpsOverviewTests(OpsTestCase):
    def test_a_broker_that_will_not_answer_degrades_to_unknown(self):
        self.as_staff()
        with patch('redis.from_url', side_effect=OSError('no broker')):
            body = self.client.get(reverse('admin_ops_overview')).json()
        self.assertTrue(all(lane['depth'] is None for lane in body['queues']))
        self.assertIn('catalog', body)
        self.assertIn('health', body)

    def test_catalog_totals_separate_published_from_draft(self):
        self.as_staff()
        body = self.client.get(reverse('admin_ops_overview')).json()
        self.assertEqual(body['catalog']['movie']['total'], 1)
        self.assertEqual(body['catalog']['movie']['draft'], 1)


class AuditFeedTests(OpsTestCase):
    def test_the_feed_returns_newest_first_and_filters_by_action(self):
        self.as_staff()
        self.client.post(self.desk_url(), {'action': 'archive'}, format='json')
        self.client.post(
            self.desk_url(), {'action': 'remove_link', 'url': ABR}, format='json',
        )
        body = self.client.get(reverse('admin_audit_feed')).json()
        self.assertGreaterEqual(body['count'], 2)
        self.assertEqual(body['results'][0]['action'], MovieSyncAudit.Action.MANUAL_UPDATE)
        archived = self.client.get(
            reverse('admin_audit_feed'), {'action': MovieSyncAudit.Action.ARCHIVE},
        ).json()
        self.assertTrue(all(row['action'] == 'archive' for row in archived['results']))
