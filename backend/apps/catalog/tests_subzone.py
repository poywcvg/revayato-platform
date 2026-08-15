from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.catalog.subzone import (
    _parse_farsi_items,
    _score_search_hit,
    _season_slug_matches,
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

    def test_search_hit_prefers_exact_title_year(self):
        exact = _score_search_hit(
            '/subtitles/interstellar',
            'Interstellar (2014)',
            title='Interstellar',
            year=2014,
        )
        wars = _score_search_hit(
            '/subtitles/interstellar-wars',
            'Interstellar Wars (2016)',
            title='Interstellar',
            year=2014,
        )
        self.assertGreater(exact, wars)

    def test_season_slug_matches_ordinal_pages(self):
        self.assertTrue(_season_slug_matches(
            '/subtitles/breaking-bad-fifth-season',
            title='Breaking Bad',
            season=5,
        ))
        self.assertFalse(_season_slug_matches(
            '/subtitles/breaking-bad-first-season',
            title='Breaking Bad',
            season=5,
        ))

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
