from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from unittest import mock

from apps.catalog import subzone
from apps.catalog.subzone import (
    SubzoneError,
    _movie_page_candidates,
    _parse_farsi_items,
    _robots_allows,
    _season_page_candidates,
    _slugify_title,
    find_movie_subtitle,
)


FARSI_LIST_HTML = """
<ul>
  <li class='item '>
    <div class='col-info'>
      <ul class='scrolllist'>
        <li>Interstellar.2014.720p.BluRay.x264</li>
        <li>Interstellar.2014.1080p.BluRay.x264</li>
      </ul>
    </div>
    <a class='download icon-download' href='/subtitles/interstellar/farsi_persian/1833997'></a>
  </li>
  <li class='item '>
    <div class='col-info'>
      <ul class='scrolllist'>
        <li>Interstellar.2014.WEB-DL.720p</li>
      </ul>
    </div>
    <a class='download icon-download' href='/subtitles/interstellar/farsi_persian/999'></a>
  </li>
</ul>
"""


@override_settings(
    SUBZONE_ENABLED=True,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class SubzoneParserTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_parse_farsi_items_extracts_releases(self):
        items = _parse_farsi_items(FARSI_LIST_HTML)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0][0], '/subtitles/interstellar/farsi_persian/1833997')
        self.assertIn('Interstellar.2014.720p.BluRay.x264', items[0][1])

    def test_slug_folds_accents_and_apostrophes(self):
        self.assertEqual(_slugify_title('Çukur'), 'cukur')
        self.assertEqual(_slugify_title("The Queen's Gambit"), 'the-queens-gambit')
        self.assertEqual(_slugify_title("Bize Bi'Şey Olmaz"), 'bize-bisey-olmaz')
        self.assertEqual(_slugify_title('Spider-Man: No Way Home'), 'spider-man-no-way-home')
        self.assertEqual(_slugify_title('Fast & Furious'), 'fast-and-furious')

    def test_movie_candidates_try_year_slug_first(self):
        urls = _movie_page_candidates(['The Batman', 'The Batman'], 2022)
        self.assertEqual(urls, [
            'https://subzone.ir/subtitles/the-batman-2022',
            'https://subzone.ir/subtitles/the-batman',
        ])

    def test_season_candidates_use_ordinal_word(self):
        urls = _season_page_candidates(['From'], 1, 2022)
        self.assertEqual(urls[0], 'https://subzone.ir/subtitles/from-first-season')
        self.assertIn('https://subzone.ir/subtitles/from-2022-first-season', urls)
        self.assertEqual(
            _season_page_candidates(['Breaking Bad'], 5, None),
            ['https://subzone.ir/subtitles/breaking-bad-fifth-season'],
        )
        self.assertEqual(_season_page_candidates(['X'], 99, None), [])

    def test_robots_gate_blocks_search_even_without_robots_txt(self):
        with mock.patch.object(subzone, '_robots_text', return_value=None):
            self.assertFalse(_robots_allows('https://subzone.ir/subtitles/searchbytitle?query=x'))
            self.assertTrue(_robots_allows('https://subzone.ir/subtitles/from-first-season'))
            # The download CDN is a different site with its own rules.
            self.assertTrue(_robots_allows('https://media.sub-api.ir/subtitles/searchbytitle'))

    def test_robots_gate_honours_live_rules(self):
        robots = 'User-agent: *\nDisallow: /private/\n'
        with mock.patch.object(subzone, '_robots_text', return_value=robots):
            self.assertFalse(_robots_allows('https://subzone.ir/private/page'))
            self.assertTrue(_robots_allows('https://subzone.ir/subtitles/interstellar'))

    def test_fetch_refuses_disallowed_path_before_network(self):
        with mock.patch.object(subzone, 'build_opener') as opener:
            with self.assertRaises(SubzoneError):
                subzone._fetch(
                    'https://subzone.ir/subtitles/searchbytitle?query=from',
                    max_bytes=1024, timeout_seconds=5,
                )
            opener.assert_not_called()

    @override_settings(SUBZONE_ENABLED=False)
    def test_disabled_provider_returns_none(self):
        movie = type('M', (), {
            'imdb_id': 'tt0816692',
            'release_year': 2014,
            'original_title': 'Interstellar',
            'title': 'Interstellar',
        })()
        self.assertIsNone(find_movie_subtitle(
            movie,
            video_urls=['https://cdn.example/Soft/Interstellar.2014.720p.mkv'],
            timeout_seconds=5,
        ))
