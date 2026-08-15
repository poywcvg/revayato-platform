"""Tests for Film2Media series season-tab / quality parsing."""

from django.test import SimpleTestCase

from apps.catalog.provider_import.providers.myf2m_parser import parse_download_links


SERIES_SEASON_HTML = '''
<html><body>
<button data-bs-target="#season-dlbox1">فصل 1</button>
<button data-bs-target="#season-dlbox2">فصل 2</button>
<div id="season-dlbox1" class="download-season">
  <div class="download-list softsub">
    <ul>
      <li>
        <span class="text">720p</span>
        <a href="https://cdn.example/Series/Show/S01/Show.E01.720p.SoftSub.mkv"
           onclick="handleDownloadClick('https://cdn.example/Series/Show/S01/Show.E01.720p.SoftSub.mkv')">دانلود مستقیم</a>
        قسمت ۱
      </li>
      <li>
        <span class="text">1080p</span>
        <a href="https://cdn.example/Series/Show/S01/Show.E02.1080p.SoftSub.mkv"
           onclick="handleDownloadClick('https://cdn.example/Series/Show/S01/Show.E02.1080p.SoftSub.mkv')">دانلود مستقیم</a>
        قسمت ۲
      </li>
    </ul>
  </div>
</div>
<div id="season-dlbox2" class="download-season">
  <div class="download-list softsub">
    <ul>
      <li>
        <span class="text">720p</span>
        <a href="https://cdn.example/Series/Show/S02/Show.S02E01.720p.SoftSub.mkv"
           onclick="handleDownloadClick('https://cdn.example/Series/Show/S02/Show.S02E01.720p.SoftSub.mkv')">دانلود مستقیم</a>
      </li>
      <li>
        <span class="text">1080p x265</span>
        <a href="https://cdn.example/Series/Show/S02/Show.S02E01.1080p.x265.SoftSub.mkv"
           onclick="handleDownloadClick('https://cdn.example/Series/Show/S02/Show.S02E01.1080p.x265.SoftSub.mkv')">دانلود مستقیم</a>
      </li>
    </ul>
  </div>
</div>
</body></html>
'''


class MyF2MSeriesParserTests(SimpleTestCase):
    def test_season_tabs_stamp_season_and_episode(self):
        parsed = parse_download_links(SERIES_SEASON_HTML, page_path='/series/show/')
        rows = parsed['available_links']
        self.assertGreaterEqual(len(rows), 4)

        s1 = [row for row in rows if row.get('season_number') == 1]
        self.assertGreaterEqual(len(s1), 2)
        episodes = sorted({row.get('episode_number') for row in s1})
        self.assertEqual(episodes, [1, 2])
        self.assertTrue(all(row.get('quality') for row in s1))

        s2e1 = [
            row for row in rows
            if row.get('season_number') == 2 and row.get('episode_number') == 1
        ]
        self.assertGreaterEqual(len(s2e1), 2)
        qualities = {row.get('quality') for row in s2e1}
        self.assertTrue(any(str(q).startswith('720p') for q in qualities))
        self.assertTrue(any('1080p' in str(q) for q in qualities))
        self.assertTrue(any('فصل 2' in str(row.get('label') or '') for row in s2e1))

    def test_movie_list_still_parses_without_season_tabs(self):
        html = '''
        <div class="download-list softsub">
          <li><span class="text">1080p</span>
            <a href="https://cdn.example/Movie.2024.1080p.SoftSub.mkv"
               onclick="handleDownloadClick('https://cdn.example/Movie.2024.1080p.SoftSub.mkv')">دانلود مستقیم</a>
          </li>
        </div>
        '''
        parsed = parse_download_links(html, page_path='/123/movie/')
        self.assertEqual(len(parsed['available_links']), 1)
        self.assertTrue(parsed['available_links'][0]['quality'].startswith('1080p'))
        self.assertNotIn('season_number', parsed['available_links'][0])

    def test_bare_episode_number_before_quality_uses_season_context(self):
        html = '''
        <button data-bs-target="#season-dlbox1">فصل 1</button>
        <div id="season-dlbox1" class="download-season">
          <div class="download-list softsub"><ul>
            <li><a href="https://cdn.example/Show.01.1080p.Farsi.Sub.mkv">دانلود مستقیم</a></li>
            <li><a href="https://cdn.example/Show.02.1080p.Farsi.Sub.mkv">دانلود مستقیم</a></li>
            <li><a href="https://cdn.example/Show.12.720p.Farsi.Sub.mkv">دانلود مستقیم</a></li>
          </ul></div>
        </div>
        '''
        rows = parse_download_links(html, page_path='/series/show/')['available_links']
        self.assertEqual(
            sorted({(row.get('season_number'), row.get('episode_number')) for row in rows}),
            [(1, 1), (1, 2), (1, 12)],
        )

    def test_zero_episode_token_is_not_materialized_as_episode_zero(self):
        html = '''
        <button data-bs-target="#season-dlbox1">فصل 1</button>
        <div id="season-dlbox1" class="download-season">
          <div class="download-list softsub"><ul>
            <li><a href="https://cdn.example/Show.S01E00.720p.mkv">دانلود مستقیم</a></li>
          </ul></div>
        </div>
        '''
        rows = parse_download_links(html, page_path='/series/show/')['available_links']
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].get('episode_number'))

    def test_trailer_assets_are_excluded(self):
        html = '''
        <div class="download-list hardsub">
          <a href="https://cdn.example/Movie.2026.Trailer.mp4">دانلود مستقیم</a>
          <a href="https://cdn.example/Movie.2026.1080p.WEB-DL.mkv">دانلود مستقیم</a>
        </div>
        '''
        rows = parse_download_links(html, page_path='/123/movie/')['available_links']
        self.assertEqual(len(rows), 1)
        self.assertIn('1080p', rows[0]['quality'])
