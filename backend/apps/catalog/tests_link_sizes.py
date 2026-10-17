"""Every download link shows its measured size (apps/catalog/link_sizes.py)."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.catalog import link_sizes
from apps.catalog.media_probe import Probe
from apps.catalog.models import Movie, Series

GB = 1024 ** 3
URL_A = 'https://cdn.example/film.1080p.mkv'
URL_B = 'https://cdn.example/film.720p.mp4'
SUB = 'https://cdn.example/film.fa.srt'


def _link(url, **extra):
    return {'url': url, 'quality': '1080p', 'label': 'x', **extra}


def _probe(sizes):
    def probe_url(url, *, expect='video', use_cache=True):
        size = sizes.get(url)
        if size is None:
            return Probe(url=url, verdict='unknown', reason='timeout')
        return Probe(url=url, verdict='live', content_length=size)
    return mock.patch('apps.catalog.media_probe.probe_url', side_effect=probe_url)


class _Clean(TestCase):
    """Host tallies and title locks live in the cache; no test inherits them."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)


class StampSizesTests(_Clean):
    def test_writes_label_and_bytes_only_where_missing(self):
        movie = Movie.objects.create(
            title='ف', slug='f', is_published=True,
            download_links=[_link(URL_A), _link(URL_B, size_label='900 MB')],
        )
        stamped = link_sizes.stamp_sizes(movie, {URL_A: 2 * GB, URL_B: 5 * GB})
        self.assertEqual(stamped, 1)
        movie.refresh_from_db()
        a, b = movie.download_links
        self.assertEqual(a['size_label'], '2.00 GB')
        self.assertEqual(a['size_bytes'], 2 * GB)
        self.assertEqual(b['size_label'], '900 MB')  # a provider's label is kept

    def test_tiny_answer_is_not_a_film_size(self):
        movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A)])
        link_sizes.stamp_sizes(movie, {URL_A: 4096})
        movie.refresh_from_db()
        self.assertNotIn('size_label', movie.download_links[0])
        self.assertIn('size_probed_at', movie.download_links[0])

    def test_does_not_bump_updated_at(self):
        movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A)])
        before = Movie.objects.get(pk=movie.pk).updated_at
        link_sizes.stamp_sizes(movie, {URL_A: GB})
        self.assertEqual(Movie.objects.get(pk=movie.pk).updated_at, before)

    def test_does_not_clobber_a_newer_row(self):
        movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A)])
        stale = Movie.objects.get(pk=movie.pk)
        Movie.objects.filter(pk=movie.pk).update(download_links=[_link(URL_A), _link(URL_B)])
        link_sizes.stamp_sizes(stale, {URL_A: GB})
        movie.refresh_from_db()
        self.assertEqual([i['url'] for i in movie.download_links], [URL_A, URL_B])
        self.assertEqual(movie.download_links[0]['size_label'], '1.00 GB')


class FillMissingSizesTests(_Clean):
    def test_sizes_links_and_leaves_subtitles_alone(self):
        movie = Movie.objects.create(
            title='ف', slug='f', is_published=True,
            download_links=[_link(URL_A), _link(URL_B), _link(SUB)],
        )
        with _probe({URL_A: 2 * GB, URL_B: GB}):
            result = link_sizes.fill_missing_sizes(limit=5)
        self.assertEqual(result['sized'], 2)
        movie.refresh_from_db()
        links = {i['url']: i for i in movie.download_links}
        self.assertEqual(links[URL_A]['size_label'], '2.00 GB')
        self.assertEqual(links[URL_B]['size_label'], '1.00 GB')
        self.assertNotIn('size_label', links[SUB])
        # Nothing left to do: the subtitle was marked asked, not re-queued.
        with _probe({}) as probe:
            self.assertEqual(link_sizes.fill_missing_sizes(limit=5)['titles'], 0)
            probe.assert_not_called()

    def test_refusal_waits_before_asking_again(self):
        movie = Movie.objects.create(title='ف', slug='f', is_published=True, download_links=[_link(URL_A)])
        with _probe({}):
            self.assertEqual(link_sizes.fill_missing_sizes(limit=5)['refused'], 1)
        with _probe({URL_A: GB}) as probe:
            self.assertEqual(link_sizes.fill_missing_sizes(limit=5)['titles'], 0)
            probe.assert_not_called()
        # A week later it is asked again.
        old = (timezone.now() - timedelta(days=8)).isoformat()
        movie.refresh_from_db()
        Movie.objects.filter(pk=movie.pk).update(
            download_links=[{**movie.download_links[0], 'size_probed_at': old}],
        )
        with _probe({URL_A: GB}):
            self.assertEqual(link_sizes.fill_missing_sizes(limit=5)['sized'], 1)

    def test_chart_titles_go_first_and_drafts_are_skipped(self):
        Movie.objects.create(title='پ', slug='p', is_published=True, popularity=999,
                             download_links=[_link('https://cdn.example/pop.mkv')])
        ranked = Series.objects.create(title='س', slug='s', is_published=True, imdb_rank=4,
                                       download_links=[_link('https://cdn.example/s01e01.mkv')])
        Movie.objects.create(title='د', slug='d', is_published=False,
                             download_links=[_link('https://cdn.example/draft.mkv')])
        queue = link_sizes._queue(1)
        self.assertEqual([(type(o), o.pk) for o in queue], [(Series, ranked.pk)])
        self.assertNotIn('d', [getattr(o, 'slug', '') for o in link_sizes._queue(10)])

    def test_budget_ends_the_tick(self):
        for n in range(3):
            Movie.objects.create(title=f'ف{n}', slug=f'f{n}', is_published=True,
                                 download_links=[_link(f'https://cdn.example/{n}.mkv')])
        with _probe({}):
            self.assertEqual(link_sizes.fill_missing_sizes(limit=3, budget_seconds=0)['titles'], 0)


class VerifyTargetKeepsSizesTests(_Clean):
    def test_measured_bytes_reach_the_link(self):
        from apps.catalog import media_verification

        movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A)])
        media_verification._keep_measured_sizes(
            movie, [{'url': URL_A, 'verdict': 'live', 'bytes': 3 * GB},
                    {'url': URL_B, 'verdict': 'dead', 'bytes': 0}],
        )
        movie.refresh_from_db()
        self.assertEqual(movie.download_links[0]['size_label'], '3.00 GB')


def _geo(url):
    return Probe(url=url, verdict='unknown', reason='geo_blocked', status=200)


class SizedAtImportTests(_Clean):
    """A save that brings new links queues one sizing run for that title."""

    def _queued(self):
        return mock.patch('apps.catalog.tasks.size_title_links_task.apply_async')

    def setUp(self):
        super().setUp()
        depth = mock.patch('apps.catalog.link_sizes._queue_depth', return_value=0)
        depth.start()
        self.addCleanup(depth.stop)

    def test_new_links_queue_one_run_after_commit(self):
        with self._queued() as apply_async, self.captureOnCommitCallbacks(execute=True):
            movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A)])
            movie.save()  # a burst of import saves is one run
        apply_async.assert_called_once()
        self.assertEqual(apply_async.call_args.args[0], ('catalog.movie', movie.pk))
        self.assertEqual(apply_async.call_args.kwargs['queue'], link_sizes.QUEUE)

    def test_saves_that_do_not_touch_links_queue_nothing(self):
        movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A)])
        cache.clear()  # that create's own run was never started; drop its lock
        with self._queued() as apply_async, self.captureOnCommitCallbacks(execute=True):
            movie.save(update_fields=['title'])
            Series.objects.create(title='س', slug='s', download_links=[_link(URL_B, size_label='1 GB')])
        apply_async.assert_not_called()

    def test_deep_queue_leaves_the_title_to_the_sweep(self):
        with mock.patch('apps.catalog.link_sizes._queue_depth', return_value=link_sizes.QUEUE_MAX_DEPTH), \
                self._queued() as apply_async, self.captureOnCommitCallbacks(execute=True):
            movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A)])
        apply_async.assert_not_called()
        # The lock went with it, so the next import save may try again.
        self.assertTrue(cache.add(f'linksize:title:catalog.movie:{movie.pk}', 1, 5))

    def test_run_sizes_every_link_of_a_long_series(self):
        urls = [f'https://cdn.example/s01e{n:02d}.1080p.mkv' for n in range(80)]
        series = Series.objects.create(title='س', slug='s', download_links=[_link(u) for u in urls])
        with _probe({u: GB for u in urls}), self._queued() as apply_async:
            result = link_sizes.run_title_sizing('catalog.series', series.pk)
        self.assertEqual(result['sized'], 80)
        apply_async.assert_not_called()
        series.refresh_from_db()
        self.assertTrue(all(i['size_label'] == '1.00 GB' for i in series.download_links))

    def test_lapsed_signature_is_marked_asked_not_retried_forever(self):
        url = 'https://cdn.example/f.mp4?expires=1'
        movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(url)])
        lapsed = Probe(url=url, verdict='unknown', reason='signature_expired')
        with mock.patch('apps.catalog.media_probe.probe_url', return_value=lapsed), \
                self._queued() as apply_async:
            result = link_sizes.run_title_sizing('catalog.movie', movie.pk)
        self.assertEqual(result['left'], 0)
        apply_async.assert_not_called()
        movie.refresh_from_db()
        self.assertIn('size_probed_at', movie.download_links[0])
        self.assertNotIn('size_label', movie.download_links[0])

    def test_out_of_time_links_stay_pending_and_run_again(self):
        movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A), _link(URL_B)])
        # URL_B is reached after the run's deadline: _measure answers None.
        measure = mock.patch('apps.catalog.link_sizes._measure',
                             side_effect=lambda url, deadline=None: GB if url == URL_A else None)
        with measure, self._queued() as apply_async, self.captureOnCommitCallbacks(execute=True):
            result = link_sizes.run_title_sizing('catalog.movie', movie.pk)
        self.assertEqual((result['sized'], result['left']), (1, 1))
        apply_async.assert_called_once()
        movie.refresh_from_db()
        links = {i['url']: i for i in movie.download_links}
        self.assertEqual(links[URL_A]['size_label'], '1.00 GB')
        self.assertNotIn('size_probed_at', links[URL_B])


class HostRefusalTests(_Clean):
    def test_a_host_that_never_sizes_stops_being_asked(self):
        blocked = [f'https://geo.example/f{n}.mkv' for n in range(link_sizes.HOST_MIN_TRIES + 5)]
        good = 'https://cdn.example/ok.mkv'
        movie = Movie.objects.create(
            title='ف', slug='f', is_published=True,
            download_links=[_link(u) for u in blocked] + [_link(good)],
        )
        asked = []

        def probe_url(url, *, expect='video', use_cache=True):
            asked.append(url)
            return Probe(url=url, verdict='live', content_length=GB) if url == good else _geo(url)

        with mock.patch('apps.catalog.media_probe.probe_url', side_effect=probe_url):
            for url in blocked[: link_sizes.HOST_MIN_TRIES]:
                link_sizes._measure(url)
            self.assertTrue(link_sizes.host_refuses('geo.example'))
            asked.clear()
            result = link_sizes.size_title(movie)
        self.assertEqual(asked, [good])
        self.assertEqual(result['host_refuses'], len(blocked))
        movie.refresh_from_db()
        links = {i['url']: i for i in movie.download_links}
        self.assertEqual(links[good]['size_label'], '1.00 GB')
        # Marked asked — never given a size nobody measured …
        self.assertTrue(all('size_probed_at' in links[u] and 'size_label' not in links[u] for u in blocked))
        # … and due again when the host's window ends, not a week later.
        cutoff_after_window = (
            timezone.now() - link_sizes.RETRY_AFTER + timedelta(seconds=link_sizes.HOST_WINDOW + 60)
        ).isoformat()
        self.assertEqual(link_sizes._pending_urls(movie, cutoff_after_window)[:1], [blocked[0]])
        self.assertEqual(link_sizes._pending_urls(movie, (timezone.now() - link_sizes.RETRY_AFTER).isoformat()), [])

    def test_one_sized_answer_keeps_the_host_open(self):
        with _probe({URL_A: GB}):
            link_sizes._measure(URL_A)
            for n in range(link_sizes.HOST_MIN_TRIES):
                link_sizes._measure(f'https://cdn.example/missing{n}.mkv')
        self.assertFalse(link_sizes.host_refuses('cdn.example'))


class HotFirstQueueTests(_Clean):
    def test_hot_chart_titles_come_before_top250_and_popularity(self):
        Movie.objects.create(title='پ', slug='p', is_published=True, popularity=999,
                             download_links=[_link('https://cdn.example/pop.mkv')])
        Series.objects.create(title='س', slug='s', is_published=True, imdb_rank=4,
                              download_links=[_link('https://cdn.example/s01e01.mkv')])
        hot = Movie.objects.create(title='ه', slug='h', is_published=True, tmdb_id=777,
                                   download_links=[_link('https://cdn.example/hot.mkv')])
        chart = {'movie': [{'tmdb_id': 777}], 'series': []}
        with mock.patch('apps.catalog.hot_titles.get_hot_chart', return_value=chart):
            queue = link_sizes._queue(2)
        self.assertEqual((type(queue[0]), queue[0].pk), (Movie, hot.pk))
        self.assertIs(type(queue[1]), Series)
