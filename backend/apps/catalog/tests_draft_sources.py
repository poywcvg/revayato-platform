"""Tests for the sourceless-draft hunt.

Two things here would quietly undo the feature rather than fail loudly: the
back-archive queue leaking into the viewer-facing playback repair budget, and
``playback_sources.scan`` resolving a ``no_source`` row because a title with
nothing to play reports "nothing is broken".
"""

from unittest.mock import PropertyMock, patch

from django.test import TestCase, override_settings

from apps.catalog import draft_sources, playback_sources
from apps.catalog.models import Episode, Movie, PlaybackSourceGap, Season, Series

MKV = {'url': 'https://cdn/x/movie.1080p.mkv', 'quality': '1080p'}
MP4 = {'url': 'https://cdn/x/movie.720p.x264.mp4', 'quality': '720p'}


def _movie(slug, **extra):
    extra.setdefault('title', 'فیلم')
    extra.setdefault('original_title', 'Film')
    extra.setdefault('is_published', False)
    extra.setdefault('download_links', [])
    return Movie.objects.create(slug=slug, **extra)


class HasAnySourceTests(TestCase):
    def test_a_linkless_draft_has_no_source(self):
        self.assertFalse(playback_sources.has_any_source(_movie('empty')))

    def test_an_unplayable_link_still_counts_as_a_source(self):
        # The distinction the whole module rests on: mkv_only is a *playback*
        # problem, no_source is an *archive* problem, and they are not the same row.
        movie = _movie('mkv', download_links=[MKV])
        self.assertTrue(playback_sources.has_any_source(movie))
        self.assertTrue(playback_sources.diagnose(movie)['unplayable'])

    def test_an_hls_key_with_no_url_counts(self):
        self.assertTrue(playback_sources.has_any_source(
            _movie('keyed', download_links=[{'key': 'hls/movie/master.m3u8'}]),
        ))

    def test_junk_link_entries_do_not_count(self):
        self.assertFalse(playback_sources.has_any_source(
            _movie('junk', download_links=[{'quality': '1080p'}, 'nonsense', None]),
        ))

    def test_a_series_streaming_from_its_episodes_counts(self):
        series = Series.objects.create(title='سریال', original_title='Show', slug='s1',
                                       is_published=False, download_links=[])
        self.assertFalse(playback_sources.has_any_source(series))
        season = Season.objects.create(series=series, season_number=1)
        Episode.objects.create(season=season, episode_number=1, title='E1',
                               is_published=True, video_url='hls/s1e1/master.m3u8')
        self.assertTrue(playback_sources.has_any_source(series))


class IterSourcelessDraftsTests(TestCase):
    def test_only_unpublished_linkless_titles_with_something_to_match_on(self):
        wanted = _movie('wanted')
        _movie('published', is_published=True)
        _movie('has-links', download_links=[MKV])
        _movie('no-english-title', original_title='')

        found = list(draft_sources.iter_sourceless_drafts(series=False))
        self.assertEqual([m.pk for m in found], [wanted.pk])

    def test_limit_is_honoured(self):
        for i in range(4):
            _movie(f'draft-{i}')
        self.assertEqual(len(list(draft_sources.iter_sourceless_drafts(series=False, limit=2))), 2)


class ScanTests(TestCase):
    def test_enrols_a_draft_nothing_else_owned(self):
        movie = _movie('lonely')
        stats = draft_sources.scan(series=False)
        self.assertEqual((stats['scanned'], stats['recorded']), (1, 1))
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk, content_type='movie')
        self.assertEqual(gap.reason, draft_sources.GAP_REASON)
        self.assertEqual(gap.status, PlaybackSourceGap.Status.OPEN)

    def test_reopens_a_draft_the_playback_pipeline_had_written_off(self):
        """``remediate_open_gaps`` retires the gap of any unpublished title.

        A draft enrolled while it was published therefore sits RESOLVED with no
        sources and no owner — which is how 606 of them ended up invisible.
        """
        movie = _movie('written-off')
        playback_sources.upsert_source_gap(movie, {'reason': 'mkv_only'})
        playback_sources.resolve_source_gap(movie, last_result='title_gone')

        stats = draft_sources.scan(series=False)
        self.assertEqual((stats['recorded'], stats['reopened']), (0, 1))
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk, content_type='movie')
        self.assertEqual(gap.status, PlaybackSourceGap.Status.OPEN)
        self.assertEqual(gap.reason, draft_sources.GAP_REASON)

    def test_dry_run_records_nothing(self):
        _movie('dry')
        stats = draft_sources.scan(series=False, record=False)
        self.assertEqual(stats['scanned'], 1)
        self.assertEqual(PlaybackSourceGap.objects.count(), 0)

    def test_re_scanning_leaves_an_enrolled_row_untouched(self):
        """Enrolment runs every crawler round over a head that barely changes.

        Rewriting the row each time would bump ``updated_at`` — the rotation key
        the hunt orders by — and inflate ``report_count``, which counts viewer
        reports. The scan would then be quietly rewriting the queue it feeds.
        """
        movie = _movie('steady')
        draft_sources.scan(series=False)
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk, content_type='movie')
        before = (gap.updated_at, gap.report_count)

        stats = draft_sources.scan(series=False)
        self.assertEqual(
            (stats['scanned'], stats['recorded'], stats['reopened'], stats['skipped']),
            (1, 0, 0, 1),
        )
        gap.refresh_from_db()
        self.assertEqual((gap.updated_at, gap.report_count), before)

    def test_rewrites_a_row_left_under_a_different_reason(self):
        """Its links went away after the playback pipeline judged the codecs."""
        movie = _movie('relabelled')
        playback_sources.upsert_source_gap(movie, {'reason': 'mkv_only'})

        stats = draft_sources.scan(series=False)
        self.assertEqual((stats['recorded'], stats['reopened'], stats['skipped']), (0, 1, 0))
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk, content_type='movie')
        self.assertEqual(gap.reason, draft_sources.GAP_REASON)


class BudgetSeparationTests(TestCase):
    """The back archive must never queue ahead of a broken player."""

    def test_remediate_open_gaps_ignores_no_source_rows(self):
        draft = _movie('backlog')
        draft_sources.scan(series=False)

        with patch.object(playback_sources, '_recrawl_all_providers') as crawl:
            stats = playback_sources.remediate_open_gaps(fix_limit=10)
        crawl.assert_not_called()
        self.assertEqual(stats['candidates'], 0)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=draft.pk).status,
            PlaybackSourceGap.Status.OPEN,
        )

    def test_playback_scan_does_not_resolve_a_no_source_row(self):
        """A published linkless title is not "healed"; it has nothing to play.

        `diagnose` reports unplayable=False for a title with zero sources, so the
        published scan used to read that as "healed" and resolve the row.
        """
        movie = _movie('published-linkless', is_published=True)
        playback_sources.upsert_source_gap(movie, draft_sources._sourceless_diag())

        stats = playback_sources.scan(series=False)
        self.assertEqual(stats['self_healed'], 0)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=movie.pk).status,
            PlaybackSourceGap.Status.OPEN,
        )


class HuntTests(TestCase):
    def _enrolled(self, slug='hunted'):
        movie = _movie(slug)
        draft_sources.scan(series=False)
        return movie

    def test_a_browser_safe_link_resolves_the_gap(self):
        movie = self._enrolled()

        def fake(obj):
            obj.download_links = [MP4]
            obj.save(update_fields=['download_links'])
            return {'myf2m': ('ok', 1)}

        with patch.object(draft_sources, '_recrawl_all_providers', side_effect=fake):
            stats = draft_sources.hunt_open_gaps(limit=5)
        self.assertEqual(stats['sourced'], 1)
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk)
        self.assertEqual(gap.status, PlaybackSourceGap.Status.RESOLVED)
        self.assertEqual(gap.last_result, 'sourced')

    def test_an_mkv_only_result_is_handed_to_the_playback_pipeline(self):
        movie = self._enrolled('mkv-hunted')

        def fake(obj):
            obj.download_links = [MKV]
            obj.save(update_fields=['download_links'])
            return {'myf2m': ('ok', 1)}

        with patch.object(draft_sources, '_recrawl_all_providers', side_effect=fake):
            stats = draft_sources.hunt_open_gaps(limit=5)
        self.assertEqual(stats['unplayable'], 1)
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk)
        self.assertEqual(gap.reason, 'mkv_only')
        self.assertEqual(gap.status, PlaybackSourceGap.Status.OPEN)
        # …and now the other queue owns it, because it is no longer `no_source`.
        with patch.object(playback_sources, '_recrawl_all_providers',
                          return_value={'myf2m': ('ok', 0)}):
            self.assertEqual(playback_sources.remediate_open_gaps(fix_limit=5)['candidates'], 1)

    def test_no_provider_listing_marks_unavailable(self):
        movie = self._enrolled('missing-upstream')
        with patch.object(draft_sources, '_recrawl_all_providers',
                          return_value={'myf2m': ('ok', 0), 'dornatv': ('ok', 0)}):
            stats = draft_sources.hunt_open_gaps(limit=5)
        self.assertEqual(stats['unavailable'], 1)
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk)
        self.assertEqual(gap.status, PlaybackSourceGap.Status.UNAVAILABLE)
        self.assertEqual(gap.last_result, 'no_provider_listing')

    def test_a_total_provider_failure_stays_queued_for_a_retry(self):
        movie = self._enrolled('provider-down')
        with patch.object(draft_sources, '_recrawl_all_providers',
                          return_value={'myf2m': ('err', 'timeout'), 'dornatv': ('exc', 'SSLError')}):
            stats = draft_sources.hunt_open_gaps(limit=5)
        self.assertEqual(stats['provider_error'], 1)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=movie.pk).status,
            PlaybackSourceGap.Status.QUEUED,
        )

    def test_every_provider_saying_not_listed_rests_the_title(self):
        # The crawls searched and found nothing; asking again next round would get
        # the same answer, so the row must rest instead of looping as an error.
        movie = self._enrolled('nowhere')
        codes = {
            'myf2m': ('err', 'myf2m_page_required'),
            'dornatv': ('err', 'dornatv_page_required'),
            'kargadan': ('err', 'kargadan_session_missing'),
        }
        with patch.object(draft_sources, '_recrawl_all_providers', return_value=codes):
            stats = draft_sources.hunt_open_gaps(limit=5)
        self.assertEqual(stats['unavailable'], 1)
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk)
        self.assertEqual(gap.status, PlaybackSourceGap.Status.UNAVAILABLE)
        self.assertEqual(gap.last_result, 'no_provider_listing')

    def test_one_failing_provider_keeps_the_title_queued(self):
        movie = self._enrolled('half-down')
        codes = {'myf2m': ('err', 'myf2m_crawl_failed'), 'dornatv': ('err', 'dornatv_page_required')}
        with patch.object(draft_sources, '_recrawl_all_providers', return_value=codes):
            stats = draft_sources.hunt_open_gaps(limit=5)
        self.assertEqual(stats['provider_error'], 1)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=movie.pk).status,
            PlaybackSourceGap.Status.QUEUED,
        )

    def test_a_provider_we_cannot_ask_alone_is_not_an_answer(self):
        movie = self._enrolled('no-cookie')
        with patch.object(draft_sources, '_recrawl_all_providers',
                          return_value={'kargadan': ('err', 'kargadan_session_missing')}):
            stats = draft_sources.hunt_open_gaps(limit=5)
        self.assertEqual(stats['provider_error'], 1)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=movie.pk).status,
            PlaybackSourceGap.Status.QUEUED,
        )

    def test_unavailable_rows_are_not_re_asked_before_the_retry_window(self):
        self._enrolled('patient')
        with patch.object(draft_sources, '_recrawl_all_providers', return_value={'myf2m': ('ok', 0)}):
            draft_sources.hunt_open_gaps(limit=5)
            second = draft_sources.hunt_open_gaps(limit=5, retry_hours=168)
        self.assertEqual(second['candidates'], 0)

    def test_dry_run_never_touches_a_provider(self):
        self._enrolled('untouched')
        with patch.object(draft_sources, '_recrawl_all_providers') as crawl:
            stats = draft_sources.hunt_open_gaps(limit=5, dry_run=True)
        crawl.assert_not_called()
        self.assertEqual(stats['skipped'], 1)

    def test_a_draft_sourced_elsewhere_closes_without_a_crawl(self):
        movie = self._enrolled('overtaken')
        movie.download_links = [MP4]
        movie.save(update_fields=['download_links'])
        with patch.object(draft_sources, '_recrawl_all_providers') as crawl:
            stats = draft_sources.hunt_open_gaps(limit=5)
        crawl.assert_not_called()
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=movie.pk).status,
            PlaybackSourceGap.Status.RESOLVED,
        )

    def test_a_deleted_draft_retires_its_row(self):
        movie = self._enrolled('deleted')
        pk = movie.pk
        movie.delete()
        stats = draft_sources.hunt_open_gaps(limit=5)
        self.assertEqual(stats['vanished'], 1)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=pk).last_result, 'title_gone',
        )


class PublishTests(TestCase):
    """A sourced draft only goes live through the gate that is actually enforced."""

    def _ready_draft(self, slug='ready', **extra):
        extra.setdefault('metadata_source', 'tmdb')
        return _movie(slug, description='توضیح فارسی کامل برای انتشار.',
                      download_links=[MP4], **extra)

    def _gate_open(self, model=Movie):
        """The real gate is tested in completeness/media tests; here it just says yes."""
        return (
            patch.object(model, 'auto_publish_blockers', new_callable=PropertyMock, return_value=[]),
            patch('apps.catalog.media_verification.ensure_verified'),
        )

    @override_settings(CATALOG_AUTO_PUBLISH=False)
    def test_nothing_is_published_while_auto_publish_is_off(self):
        movie = self._ready_draft()
        blockers, verify = self._gate_open()
        with blockers, verify:
            self.assertFalse(draft_sources.maybe_publish(movie))
        movie.refresh_from_db()
        self.assertFalse(movie.is_published)

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_an_incomplete_draft_is_still_refused(self):
        movie = self._ready_draft()  # no poster, no genres, no cast, no rating
        with patch('apps.catalog.media_verification.ensure_verified'):
            self.assertFalse(draft_sources.maybe_publish(movie))
        self.assertTrue(movie.auto_publish_blockers)

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_a_complete_crawler_draft_needs_no_per_row_flag(self):
        # `auto_publish` is only ever set by the TMDB date-window sync, so asking
        # for it kept every chart-crawler draft the hunter filled offline.
        movie = self._ready_draft(auto_publish=False)
        PlaybackSourceGap.objects.create(content_type='movie', object_id=movie.pk, episode_id=0,
                                         reason=draft_sources.GAP_REASON,
                                         status=PlaybackSourceGap.Status.RESOLVED,
                                         last_result='sourced')
        blockers, verify = self._gate_open()
        with blockers, verify:
            self.assertTrue(draft_sources.maybe_publish(movie))
        movie.refresh_from_db()
        self.assertTrue(movie.is_published)
        self.assertEqual(movie.publication_status, Movie.PublicationStatus.PUBLISHED)
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk)
        self.assertEqual(gap.last_result, draft_sources.PUBLISHED_RESULT)

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_a_complete_series_is_published_through_the_same_gate(self):
        series = Series.objects.create(title='سریال', original_title='Show', slug='s-pub',
                                       is_published=False, download_links=[MP4],
                                       metadata_source='tmdb')
        blockers, verify = self._gate_open(Series)
        with blockers, verify:
            self.assertTrue(draft_sources.maybe_publish(series))
        series.refresh_from_db()
        self.assertTrue(series.is_published)

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_a_hand_made_draft_is_left_for_a_human(self):
        movie = self._ready_draft('manual', metadata_source='manual')
        blockers, verify = self._gate_open()
        with blockers, verify:
            self.assertFalse(draft_sources.maybe_publish(movie))

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_an_archived_movie_stays_archived(self):
        movie = self._ready_draft('arch', publication_status=Movie.PublicationStatus.ARCHIVED)
        blockers, verify = self._gate_open()
        with blockers, verify:
            self.assertFalse(draft_sources.maybe_publish(movie))

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_a_title_an_admin_put_back_to_draft_is_not_overruled(self):
        from apps.catalog.models import MovieSyncAudit

        series = Series.objects.create(title='سریال', original_title='Show', slug='s-held',
                                       is_published=False, download_links=[MP4],
                                       metadata_source='tmdb')
        MovieSyncAudit.objects.create(action=MovieSyncAudit.Action.MANUAL_UPDATE,
                                      details={'kind': 'series', 'object_id': series.pk,
                                               'state': 'draft'})
        blockers, verify = self._gate_open(Series)
        with blockers, verify:
            self.assertFalse(draft_sources.maybe_publish(series))


class PublishSourcedDraftsTests(TestCase):
    """The per-round pass that re-asks the gate once metadata caught up."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def _gap(self, obj, **extra):
        extra.setdefault('reason', draft_sources.GAP_REASON)
        extra.setdefault('status', PlaybackSourceGap.Status.RESOLVED)
        extra.setdefault('last_result', 'sourced')
        kind = 'series' if isinstance(obj, Series) else 'movie'
        return PlaybackSourceGap.objects.create(content_type=kind, object_id=obj.pk,
                                                episode_id=0, **extra)

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_only_drafts_the_hunter_sourced_are_asked(self):
        sourced = _movie('sourced', download_links=[MP4], metadata_source='tmdb')
        self._gap(sourced)
        unplayable = _movie('mkv-draft', download_links=[MKV], metadata_source='tmdb')
        self._gap(unplayable, reason='mkv_only', status=PlaybackSourceGap.Status.OPEN,
                  last_result='sourced_unplayable')
        still_empty = _movie('empty-draft', metadata_source='tmdb')
        self._gap(still_empty, status=PlaybackSourceGap.Status.UNAVAILABLE,
                  last_result='no_provider_listing')
        done = _movie('done', download_links=[MP4], metadata_source='tmdb')
        self._gap(done, last_result=draft_sources.PUBLISHED_RESULT)
        # A published title's codec gap is the playback pipeline's, not ours.
        live = _movie('live', download_links=[MKV], metadata_source='tmdb', is_published=True)
        self._gap(live, reason='mkv_only', status=PlaybackSourceGap.Status.OPEN,
                  last_result='queued')

        with patch.object(draft_sources, 'maybe_publish', return_value=True) as gate, \
                patch('apps.catalog.cache.bump_catalog_cache_version'):
            stats = draft_sources.publish_sourced_drafts(limit=10)
        asked = {call.args[0].pk for call in gate.call_args_list}
        self.assertEqual(asked, {sourced.pk, unplayable.pk})
        self.assertEqual(stats['published'], 2)

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_a_blocked_draft_rests_instead_of_eating_every_pass(self):
        movie = _movie('blocked', download_links=[MP4], metadata_source='tmdb')
        self._gap(movie)
        with patch.object(draft_sources, 'maybe_publish', return_value=False) as gate:
            first = draft_sources.publish_sourced_drafts(limit=10)
            second = draft_sources.publish_sourced_drafts(limit=10)
        self.assertEqual(gate.call_count, 1)
        self.assertEqual(first['blocked'], 1)
        self.assertEqual(second['resting'], 1)


class PublishReadyMoviesTests(TestCase):
    """The periodic publish pass was a permanent no-op; this is that regression."""

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_rights_verified_no_longer_blocks_a_movie_that_clears_the_real_gate(self):
        from apps.catalog.ingestion import publish_ready_movies

        movie = _movie('gate', description='توضیح', download_links=[MP4],
                       auto_publish=True, rights_verified=False)
        with patch('apps.catalog.ingestion.maybe_auto_publish') as gate:
            def publish(m, *, enabled):
                m.is_published = True
                m.publication_status = Movie.PublicationStatus.PUBLISHED
                return True

            gate.side_effect = publish
            self.assertEqual(publish_ready_movies(enabled=True), 1)
        self.assertEqual(gate.call_args.args[0].pk, movie.pk)
        movie.refresh_from_db()
        self.assertTrue(movie.is_published)

    @override_settings(CATALOG_AUTO_PUBLISH=True)
    def test_limit_caps_one_pass(self):
        from apps.catalog.ingestion import publish_ready_movies

        for i in range(3):
            _movie(f'cap-{i}', download_links=[MP4], auto_publish=True)
        with patch('apps.catalog.ingestion.maybe_auto_publish', return_value=False) as gate:
            publish_ready_movies(enabled=True, limit=2)
        self.assertEqual(gate.call_count, 2)
