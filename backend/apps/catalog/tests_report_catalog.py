"""Tests for the «گزارش خطا» button catalogue and the repairs behind it.

The point of splitting the old six buttons into twelve was precision: each
button names one symptom because one *distinct* repair addresses it. These
tests pin both halves of that promise —

* the catalogue and the dispatch table cannot drift apart (a button that claims
  an automatic fix must have one, and every handler must be reachable);
* each new handler reaches the honest verdict, in particular that it reports
  ``needs_review`` instead of ``resolved`` when it could not confirm the
  viewer's symptom is actually gone.
"""

from unittest.mock import patch

from django.test import TestCase

from apps.catalog import content_remediation as remediation
from apps.catalog import report_catalog
from apps.catalog.models import ContentIssueReport, Episode, Movie, Season, Series


class CatalogueShapeTests(TestCase):
    """Invariants a client can rely on when it renders the buttons."""

    def test_every_button_belongs_to_a_declared_group(self):
        known = {key for key, _ in report_catalog.GROUPS}
        for button in report_catalog.BUTTONS:
            self.assertIn(button['group'], known, button['value'])

    def test_every_button_is_fully_populated(self):
        for button in report_catalog.BUTTONS:
            for field in ('value', 'group', 'label', 'hint', 'icon', 'scope'):
                self.assertTrue(button.get(field), f'{button["value"]}.{field}')
            self.assertIn(button['scope'], {'both', 'movie', 'series'})
            self.assertIsInstance(button['auto'], bool)

    def test_labels_cover_the_retired_spellings_too(self):
        # A ticket subject is rendered from a stored problem_type, which may be
        # an old row's coarse value.
        for value in report_catalog.VALID_PROBLEMS:
            self.assertIn(value, report_catalog.PROBLEM_LABELS)

    def test_legacy_aliases_point_at_real_buttons(self):
        for old, new in report_catalog.LEGACY_ALIASES.items():
            self.assertNotIn(old, report_catalog.BY_VALUE)
            self.assertIn(new, report_catalog.BY_VALUE)

    def test_normalize_maps_legacy_and_never_rejects(self):
        self.assertEqual(report_catalog.normalize('subtitle'), 'subtitle_missing')
        self.assertEqual(report_catalog.normalize('AUDIO'), 'audio_silent')
        self.assertEqual(report_catalog.normalize('subtitle_sync'), 'subtitle_sync')
        # A viewer telling us something is broken is never dropped on the floor.
        self.assertEqual(report_catalog.normalize('brand_new_symptom'), 'other')
        self.assertEqual(report_catalog.normalize(''), 'other')

    def test_wrong_episode_is_offered_only_where_it_can_be_acted_on(self):
        movie = {b['value'] for b in report_catalog.buttons_for('movie')}
        self.assertNotIn('wrong_episode', movie)

        blind = {b['value'] for b in report_catalog.buttons_for('series')}
        self.assertNotIn('wrong_episode', blind)

        scoped = {b['value'] for b in report_catalog.buttons_for('series', has_episode=True)}
        self.assertIn('wrong_episode', scoped)

    def test_grouped_for_drops_groups_that_emptied(self):
        groups = report_catalog.grouped_for('movie')
        self.assertTrue(groups)
        for group in groups:
            self.assertTrue(group['options'])
        flat = [option['value'] for group in groups for option in group['options']]
        self.assertEqual(sorted(flat), sorted(b['value'] for b in report_catalog.buttons_for('movie')))

    def test_buttons_for_returns_copies(self):
        # A caller mutating its own response must not rewrite the catalogue.
        report_catalog.buttons_for()[0]['label'] = 'tampered'
        self.assertNotEqual(report_catalog.BUTTONS[0]['label'], 'tampered')


class CatalogueMatchesDispatchTests(TestCase):
    """The catalogue and the remediation engine are one contract, not two."""

    def test_every_auto_button_has_a_handler(self):
        for value in report_catalog.AUTO_PROBLEMS:
            self.assertIn(value, remediation._DISPATCH, f'{value} promises an auto-fix with no handler')

    def test_no_handler_is_unreachable(self):
        for value in remediation._DISPATCH:
            self.assertIn(value, report_catalog.VALID_PROBLEMS, f'{value} can never be posted')

    def test_other_has_no_automatic_repair(self):
        self.assertNotIn('other', report_catalog.AUTO_PROBLEMS)
        self.assertNotIn('other', remediation._DISPATCH)

    def test_legacy_values_still_dispatch(self):
        for old in report_catalog.LEGACY_ALIASES:
            self.assertIn(old, remediation._DISPATCH)

    def test_model_choices_accept_every_catalogue_value(self):
        choices = {value for value, _ in ContentIssueReport.Problem.choices}
        self.assertTrue(report_catalog.VALID_PROBLEMS <= choices)

    def test_model_auto_problems_come_from_the_catalogue(self):
        self.assertEqual(ContentIssueReport.AUTO_PROBLEMS, report_catalog.AUTO_PROBLEMS)


class _HandlerBase(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(
            title='فیلم', slug='film', video_url='https://cdn.example/film.1080p.mp4',
            download_links=[{'url': 'https://cdn.example/film.1080p.mp4', 'quality': '1080p'}],
        )

    def report(self, problem_type, **kw):
        return ContentIssueReport.objects.create(
            content_type='movie', object_id=self.movie.pk, problem_type=problem_type,
            slug='film', title='فیلم', **kw,
        )

    def run_handler(self, report):
        return remediation._DISPATCH[report.problem_type](report, self.movie, None)


class BufferingTests(_HandlerBase):
    def test_healthy_mirrors_are_not_churned(self):
        report = self.report('buffering')
        verdict = {'status': 'passed', 'reason': '', 'checked': 3, 'dead': 0, 'downloadable': True}
        with patch('apps.catalog.media_verification.verify_target', return_value=verdict), \
                patch('apps.catalog.playback_sources.remediate') as recrawl:
            self.run_handler(report)
        recrawl.assert_not_called()
        self.assertEqual(report.status, 'needs_review')
        self.assertIn('all_sources_healthy', report.last_result)

    def test_dead_mirrors_are_pruned_then_recrawled(self):
        report = self.report('buffering')
        verdict = {'status': 'failed', 'reason': 'dead', 'checked': 3, 'dead': 2, 'downloadable': False}
        with patch('apps.catalog.media_verification.verify_target', return_value=verdict), \
                patch('apps.catalog.playback_sources.remediate', return_value={'outcome': 'ok'}), \
                patch.object(remediation, 'target_playable', return_value=True):
            self.run_handler(report)
        self.assertEqual(report.status, 'resolved')
        self.assertIsNotNone(report.remediated_at)
        self.assertEqual(report.meta['probe']['dead'], 2)

    def test_pruned_but_still_unplayable_stays_open(self):
        report = self.report('buffering')
        verdict = {'status': 'failed', 'reason': 'dead', 'checked': 3, 'dead': 2, 'downloadable': False}
        with patch('apps.catalog.media_verification.verify_target', return_value=verdict), \
                patch('apps.catalog.playback_sources.remediate', return_value={'outcome': 'queued'}), \
                patch.object(remediation, 'target_playable', return_value=False):
            self.run_handler(report)
        self.assertEqual(report.status, 'queued')
        self.assertIsNone(report.remediated_at)


class AudioSilentTests(_HandlerBase):
    def test_a_codec_browsers_decode_is_not_our_bug(self):
        report = self.report('audio_silent')
        tech = {'verdict': 'safe', 'audio': 'aac', 'video': 'h264'}
        with patch('apps.catalog.media_tech.verify_source', return_value=tech), \
                patch('apps.catalog.playback_sources.remediate') as recrawl:
            self.run_handler(report)
        recrawl.assert_not_called()
        self.assertEqual(report.status, 'needs_review')
        self.assertIn('aac', report.last_result)

    def test_dts_is_recrawled_and_resolved_only_when_the_new_track_is_decodable(self):
        report = self.report('audio_silent')
        before = {'verdict': 'unsafe', 'audio': 'dts', 'video': 'h264'}
        after = {'verdict': 'safe', 'audio': 'aac', 'video': 'h264'}

        def swap(*args, **kwargs):
            # The crawler landing a new mirror is what changes video_url.
            self.movie.video_url = 'https://cdn.example/film.aac.mp4'
            self.movie.save(update_fields=['video_url'])
            return {'outcome': 'replaced'}

        with patch('apps.catalog.media_tech.verify_source', side_effect=[before, after]), \
                patch('apps.catalog.playback_sources.remediate', side_effect=swap):
            self.run_handler(report)
        self.assertEqual(report.status, 'resolved')
        self.assertIn('aac', report.last_result)

    def test_no_decodable_mirror_is_reported_as_unavailable_not_fixed(self):
        report = self.report('audio_silent')
        tech = {'verdict': 'unsafe', 'audio': 'truehd', 'video': 'h264'}
        with patch('apps.catalog.media_tech.verify_source', return_value=tech), \
                patch('apps.catalog.playback_sources.remediate', return_value={'outcome': 'none'}):
            self.run_handler(report)
        self.assertEqual(report.status, 'unavailable')
        self.assertIn('no_browser_safe_audio', report.last_result)
        self.assertIsNone(report.remediated_at)
        # The gateway can remux this on demand, but only if the player is told to.
        self.assertTrue(report.meta['requires_gateway'])

    def test_an_unreadable_source_is_retried_not_condemned(self):
        report = self.report('audio_silent')
        tech = {'verdict': 'unknown', 'reason': 'timeout'}
        with patch('apps.catalog.media_tech.verify_source', return_value=tech), \
                patch('apps.catalog.playback_sources.remediate') as recrawl:
            self.run_handler(report)
        recrawl.assert_not_called()
        self.assertEqual(report.status, 'queued')


class AudioDesyncTests(_HandlerBase):
    def test_a_different_encode_is_offered_for_confirmation(self):
        report = self.report('audio_desync')

        def swap(*args, **kwargs):
            self.movie.video_url = 'https://cdn.example/film.other.mp4'
            self.movie.save(update_fields=['video_url'])
            return {'outcome': 'replaced'}

        with patch('apps.catalog.playback_sources.remediate', side_effect=swap):
            self.run_handler(report)
        # Never "resolved": only the viewer can tell us the drift is gone.
        self.assertEqual(report.status, 'queued')

    def test_no_alternative_encode_goes_to_a_human(self):
        with patch('apps.catalog.playback_sources.remediate', return_value={'outcome': 'none'}):
            report = self.report('audio_desync')
            self.run_handler(report)
        self.assertEqual(report.status, 'needs_review')


class SubtitleTests(_HandlerBase):
    def setUp(self):
        super().setUp()
        self.movie.subtitle_tracks = [{'src': '/media/subs/film.vtt', 'lang': 'fa'}]
        self.movie.save(update_fields=['subtitle_tracks'])

    def test_a_mistimed_track_is_re_run_without_being_deleted(self):
        report = self.report('subtitle_sync')
        with patch(
            'apps.catalog.playback_subtitle.ensure_playback_subtitles',
            return_value={'status': 'ready'},
        ) as ensure:
            self.run_handler(report)
        ensure.assert_called_once()
        self.movie.refresh_from_db()
        self.assertTrue(self.movie.subtitle_tracks)
        self.assertEqual(report.status, 'resolved')

    def test_a_garbled_track_is_deleted_first_or_the_pipeline_re_serves_it(self):
        report = self.report('subtitle_garbled')
        seen = {}

        def ensure(**kwargs):
            self.movie.refresh_from_db()
            seen['tracks_at_call'] = list(self.movie.subtitle_tracks or [])
            return {'status': 'ready'}

        with patch('apps.catalog.playback_subtitle.ensure_playback_subtitles', side_effect=ensure):
            self.run_handler(report)
        self.assertEqual(seen['tracks_at_call'], [])
        self.assertEqual(report.meta['dropped_tracks'], 1)
        self.assertEqual(report.status, 'resolved')

    def test_a_pipeline_that_only_queued_is_not_called_resolved(self):
        report = self.report('subtitle_sync')
        with patch(
            'apps.catalog.playback_subtitle.ensure_playback_subtitles',
            return_value={'status': 'queued', 'report_id': 7},
        ):
            self.run_handler(report)
        self.assertEqual(report.status, 'queued')
        self.assertEqual(report.meta['softsub_report_id'], 7)


class QualityTests(_HandlerBase):
    def test_a_source_that_matches_its_label_is_not_recrawled(self):
        report = self.report('quality', playback_version='1080p')
        with patch('apps.catalog.media_tech.verify_source', return_value={'height': 1080}), \
                patch('apps.catalog.playback_sources.remediate') as recrawl:
            self.run_handler(report)
        recrawl.assert_not_called()
        self.assertEqual(report.status, 'needs_review')

    def test_a_mislabelled_source_is_recrawled(self):
        report = self.report('quality', playback_version='1080p')
        with patch('apps.catalog.media_tech.verify_source', return_value={'height': 360}), \
                patch('apps.catalog.playback_sources.remediate', return_value={'outcome': 'ok'}):
            self.run_handler(report)
        self.assertEqual(report.status, 'queued')
        self.assertIn('360p_below_1080', report.last_result)


class DownloadTests(_HandlerBase):
    def test_links_that_all_serve_point_back_at_the_viewer(self):
        report = self.report('download_dead')
        verdict = {'status': 'passed', 'reason': '', 'checked': 2, 'dead': 0, 'downloadable': True}
        with patch('apps.catalog.media_verification.verify_target', return_value=verdict), \
                patch('apps.catalog.playback_sources.remediate') as recrawl:
            self.run_handler(report)
        recrawl.assert_not_called()
        self.assertEqual(report.status, 'needs_review')

    def test_unreachable_links_are_retried_rather_than_blamed(self):
        report = self.report('download_dead')
        verdict = {'status': 'unknown', 'reason': 'timeout', 'checked': 2, 'dead': 0, 'downloadable': False}
        with patch('apps.catalog.media_verification.verify_target', return_value=verdict):
            self.run_handler(report)
        self.assertEqual(report.status, 'queued')

    def test_dead_links_are_dropped_and_the_pool_refilled(self):
        report = self.report('download_dead')
        verdict = {'status': 'failed', 'reason': 'dead', 'checked': 2, 'dead': 1, 'downloadable': False}
        with patch('apps.catalog.media_verification.verify_target', return_value=verdict), \
                patch('apps.catalog.playback_sources.remediate', return_value={'outcome': 'ok'}):
            self.run_handler(report)
        self.assertEqual(report.status, 'resolved')

    def test_an_emptied_pool_is_reported_as_unavailable(self):
        self.movie.download_links = []
        self.movie.save(update_fields=['download_links'])
        report = self.report('download_dead')
        verdict = {'status': 'failed', 'reason': 'dead', 'checked': 2, 'dead': 2, 'downloadable': False}
        with patch('apps.catalog.media_verification.verify_target', return_value=verdict), \
                patch('apps.catalog.playback_sources.remediate', return_value={'outcome': 'none'}):
            self.run_handler(report)
        self.assertEqual(report.status, 'unavailable')


class EpisodeScopeTests(TestCase):
    """An episode report must repair the episode's own row, not the series."""

    def setUp(self):
        self.series = Series.objects.create(title='سریال', slug='serial')
        season = Season.objects.create(series=self.series, season_number=1)
        self.episode = Episode.objects.create(
            season=season, episode_number=3, title='قسمت ۳',
            video_url='https://cdn.example/s01e03.mkv',
            subtitle_tracks=[{'src': '/media/subs/e3.vtt', 'lang': 'fa'}],
        )

    def test_garbled_subtitle_clears_the_episode_track(self):
        report = ContentIssueReport.objects.create(
            content_type='series', object_id=self.series.pk, episode_id=self.episode.pk,
            problem_type='subtitle_garbled', slug='serial', title='سریال',
        )
        with patch(
            'apps.catalog.playback_subtitle.ensure_playback_subtitles',
            return_value={'status': 'ready'},
        ):
            remediation._DISPATCH['subtitle_garbled'](report, self.series, self.episode)
        self.episode.refresh_from_db()
        self.assertEqual(self.episode.subtitle_tracks, [])
        self.assertEqual(report.meta['dropped_tracks'], 1)


class IntakeNormalisationTests(TestCase):
    """An app built before the split must still reach a real repair."""

    def setUp(self):
        Movie.objects.create(title='فیلم', slug='film')

    def post(self, problem_type):
        return self.client.post(
            '/api/catalog/report-issue/',
            {'content_type': 'movie', 'slug': 'film', 'problem_type': problem_type},
            content_type='application/json',
        )

    def test_legacy_subtitle_is_stored_as_the_precise_button(self):
        with patch('apps.catalog.content_reports._kick_remediation', return_value=False):
            response = self.post('subtitle')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['problem_type'], 'subtitle_missing')
        self.assertTrue(ContentIssueReport.objects.filter(problem_type='subtitle_missing').exists())

    def test_an_unknown_problem_type_is_still_rejected_at_the_edge(self):
        response = self.post('not_a_button')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_payload')


class OptionsEndpointTests(TestCase):
    """What a client actually receives when it asks for the buttons."""

    def test_movie_options_omit_the_episode_button(self):
        response = self.client.get('/api/catalog/report-issue/options/', {'content_type': 'movie'})
        self.assertEqual(response.status_code, 200)
        values = {option['value'] for option in response.json()['options']}
        self.assertNotIn('wrong_episode', values)
        self.assertIn('audio_silent', values)

    def test_a_scoped_episode_unlocks_the_episode_button(self):
        response = self.client.get(
            '/api/catalog/report-issue/options/', {'content_type': 'series', 'episode_id': '12'},
        )
        values = {option['value'] for option in response.json()['options']}
        self.assertIn('wrong_episode', values)

    def test_groups_and_flat_options_agree(self):
        payload = self.client.get('/api/catalog/report-issue/options/').json()
        flat = [option['value'] for group in payload['groups'] for option in group['options']]
        self.assertEqual(flat, [option['value'] for option in payload['options']])

    def test_every_served_option_is_one_intake_accepts(self):
        payload = self.client.get('/api/catalog/report-issue/options/').json()
        for option in payload['options']:
            self.assertIn(option['value'], report_catalog.VALID_PROBLEMS)
