"""Tests for the self-describing-URL contamination guard (link_integrity)."""

from types import SimpleNamespace

from django.test import TestCase

from apps.catalog.models import Movie, Series
from apps.catalog.provider_import.link_integrity import (
    classify_movie_link,
    classify_series_link,
    filter_contaminated_links,
    parse_year_title,
)

CDN = 'https://cdn.abrtech.top/yA3f'


def movie(title='', original_title='', release_year=None):
    return SimpleNamespace(title=title, original_title=original_title, release_year=release_year)


class ParseYearTitleTests(TestCase):
    def test_year_before_first_quality_token(self):
        # Real film-year is the 4-digit token immediately before the quality token.
        self.assertEqual(parse_year_title('blade.runner.2049.2017.1080p.bluray.x265')[0], 2017)
        self.assertEqual(parse_year_title('wonder.woman.1984.2020.2160p.web-dl')[0], 2020)
        self.assertEqual(parse_year_title('1917.2019.1080p.bluray')[0], 2019)

    def test_plain_leaf(self):
        yr, title = parse_year_title('dangerous.animals.2025.1080p.web-dl.x264')
        self.assertEqual(yr, 2025)
        self.assertIn('dangerous', title)


class ClassifyMovieTests(TestCase):
    def test_series_pack_on_movie_is_contamination(self):
        m = movie('The Office', 'The Office', 2005)
        url = f'{CDN}/Series/The.Office/The.Office.S03E05.1080p.mkv'
        self.assertEqual(classify_movie_link(m, url), 'A_series')

    def test_episode_marker_is_contamination(self):
        m = movie('Some Film', 'Some Film', 2020)
        self.assertEqual(
            classify_movie_link(m, f'{CDN}/Film/2020/Some.Film.S01E02.1080p.mkv'),
            'A_series',
        )

    def test_wrong_film_disjoint_title_and_year(self):
        # Disjoint title with a year gap > 1 = unambiguously a different film.
        m = movie('Dune', 'Dune', 2021)
        url = f'{CDN}/Film/2019/Joker.2019/SUB/Joker.2019.1080p.web-dl.mkv'
        self.assertEqual(classify_movie_link(m, url), 'B_wrongfilm')

    def test_offby1_disjoint_is_review_not_stripped(self):
        # شورش case: disjoint title but only 1 year off -> C_offby1. This is the
        # documented residual: the guard does NOT auto-strip it (only the named
        # FORCE cleanup did), because auto-stripping C would kill legit foreign
        # alt-titles that are one year off in metadata.
        m = movie('شورش', 'Dange', 2024)
        url = f'{CDN}/Film/2025/Dangerous.Animals.2025/SUB/Dangerous.Animals.2025.1080p.web-dl.mkv'
        self.assertEqual(classify_movie_link(m, url), 'C_offby1')

    def test_sequel_number_mismatch(self):
        m = movie('Iron Man', 'Iron Man', 2008)
        url = f'{CDN}/Film/2010/Iron.Man.2.2010/Iron.Man.2.2010.1080p.bluray.mkv'
        self.assertEqual(classify_movie_link(m, url), 'seq_diff')

    def test_remake_same_title_large_year_gap(self):
        m = movie('West Side Story', 'West Side Story', 1961)
        url = f'{CDN}/Film/2021/West.Side.Story.2021/West.Side.Story.2021.1080p.web-dl.mkv'
        self.assertEqual(classify_movie_link(m, url), 'remake')

    def test_foreign_alt_title_matching_year_is_legit(self):
        # English CDN name shares no token with the foreign catalog title, but
        # the year matches -> legitimate, must NOT be stripped.
        m = movie('خوب بد جلف', 'Il buono, il brutto, il cattivo', 1966)
        url = f'{CDN}/Film/1966/The.Good.the.Bad.and.the.Ugly.1966/The.Good.the.Bad.and.the.Ugly.1966.1080p.bluray.mkv'
        self.assertNotIn(classify_movie_link(m, url), {'A_series', 'B_wrongfilm', 'seq_diff', 'remake'})

    def test_year_in_title_not_confused(self):
        m = movie('Blade Runner 2049', 'Blade Runner 2049', 2017)
        url = f'{CDN}/Film/2017/Blade.Runner.2049.2017/Blade.Runner.2049.2017.1080p.bluray.x265.mkv'
        self.assertEqual(classify_movie_link(m, url), 'ok')

    def test_metadata_year_slip_kept(self):
        # Same base title + same sequel + small year gap = metadata slip, keep.
        m = movie('Americana', 'Americana', 2023)
        url = f'{CDN}/Film/2025/Americana.2025/Americana.2025.1080p.web-dl.mkv'
        self.assertEqual(classify_movie_link(m, url), 'same_title_yeardiff')

    def test_matching_film_is_ok(self):
        m = movie('Dune', 'Dune', 2021)
        url = f'{CDN}/Film/2021/Dune.2021/DUB/Dune.2021.1080p.web-dl.mkv'
        self.assertEqual(classify_movie_link(m, url), 'ok')


class ClassifySeriesTests(TestCase):
    def test_own_episodes_kept(self):
        s = SimpleNamespace(title='The Office', original_title='The Office')
        url = f'{CDN}/Series/The.Office/The.Office.S02E01.1080p.mkv'
        self.assertEqual(classify_series_link(s, url), 'ok')

    def test_other_series_pack_stripped(self):
        s = SimpleNamespace(title='The Office', original_title='The Office')
        url = f'{CDN}/Series/Breaking.Bad/Breaking.Bad.S01E01.1080p.mkv'
        self.assertEqual(classify_series_link(s, url), 'B_wrongfilm')

    def test_date_filed_pack_is_judged_by_its_name_not_the_year(self):
        # dlfilmz files packs by upload date: every Reacher S01 link was dropped
        # as "wrong film" because the first folder after /series/ was "2023".
        s = SimpleNamespace(title='ریچر', original_title='Reacher')
        url = f'{CDN}/series/2023/09/Reacher/s01/subbed/Reacher.S01E01.1080p.WEB-DL.mkv'
        self.assertEqual(classify_series_link(s, url), 'ok')
        other = f'{CDN}/series/2023/09/Breaking.Bad/s01/Breaking.Bad.S01E01.1080p.mkv'
        self.assertEqual(classify_series_link(s, other), 'B_wrongfilm')

    def test_a_pack_with_no_name_folder_is_kept(self):
        s = SimpleNamespace(title='The Office', original_title='The Office')
        url = f'{CDN}/Series/2021/s01/The.Office.S01E01.1080p.mkv'
        self.assertEqual(classify_series_link(s, url), 'ok')

    def test_movie_leaf_on_series_stripped(self):
        s = SimpleNamespace(title='The Office', original_title='The Office')
        url = f'{CDN}/Film/2019/Joker.2019/Joker.2019.1080p.web-dl.mkv'
        self.assertEqual(classify_series_link(s, url), 'B_wrongfilm')


class FilterContaminatedLinksTests(TestCase):
    def test_movie_filter_drops_only_contamination(self):
        m = Movie.objects.create(title='Dune', original_title='Dune', release_year=2021)
        links = [
            {'url': f'{CDN}/Film/2021/Dune.2021/Dune.2021.1080p.web-dl.mkv', 'kind': 'download'},
            {'url': f'{CDN}/Film/2019/Joker.2019/Joker.2019.1080p.web-dl.mkv'},      # B_wrongfilm
            {'url': f'{CDN}/Series/Foo/Foo.S01E01.1080p.mkv'},                        # A_series
        ]
        kept, dropped = filter_contaminated_links(m, links)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 2)
        self.assertEqual({c for _, c in dropped}, {'B_wrongfilm', 'A_series'})

    def test_non_dict_and_unclassifiable_kept(self):
        m = Movie.objects.create(title='Dune', original_title='Dune', release_year=2021)
        links = [
            'not-a-dict',
            {'url': ''},
            {'url': 'https://example.com/some/opaque/stream.m3u8'},
        ]
        kept, dropped = filter_contaminated_links(m, links)
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 3)

    def test_series_filter_keeps_own_episodes(self):
        s = Series.objects.create(title='The Office', original_title='The Office')
        links = [
            {'url': f'{CDN}/Series/The.Office/The.Office.S01E01.1080p.mkv'},
            {'url': f'{CDN}/Series/The.Office/The.Office.S01E02.1080p.mkv'},
            {'url': f'{CDN}/Series/Breaking.Bad/Breaking.Bad.S01E01.1080p.mkv'},
        ]
        kept, dropped = filter_contaminated_links(s, links)
        self.assertEqual(len(kept), 2)
        self.assertEqual(len(dropped), 1)
