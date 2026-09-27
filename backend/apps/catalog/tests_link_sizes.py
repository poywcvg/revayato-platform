"""Every download link shows its measured size (apps/catalog/link_sizes.py)."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

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


class StampSizesTests(TestCase):
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


class FillMissingSizesTests(TestCase):
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


class VerifyTargetKeepsSizesTests(TestCase):
    def test_measured_bytes_reach_the_link(self):
        from apps.catalog import media_verification

        movie = Movie.objects.create(title='ف', slug='f', download_links=[_link(URL_A)])
        media_verification._keep_measured_sizes(
            movie, [{'url': URL_A, 'verdict': 'live', 'bytes': 3 * GB},
                    {'url': URL_B, 'verdict': 'dead', 'bytes': 0}],
        )
        movie.refresh_from_db()
        self.assertEqual(movie.download_links[0]['size_label'], '3.00 GB')
