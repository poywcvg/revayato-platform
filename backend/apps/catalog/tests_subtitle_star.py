"""Unit tests for the strict SubtitleStar movie provider."""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.catalog.subtitle_star import (
    SubtitleStarMatch,
    _Response,
    _candidate_pages,
    _download_links,
    _has_exact_identity,
    _safe_zip_members,
    episode_key_from_name,
    find_movie_subtitle,
    find_series_episode_subtitles,
    latin_title_hint_from_urls,
    resolve_subtitlestar_search_title,
)


def _zip_payload(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return output.getvalue()


@override_settings(
    SUBTITLESTAR_ENABLED=True,
    SUBTITLESTAR_BASE_URL='https://subtitlestar.com',
    SUBTITLESTAR_ALLOWED_DOWNLOAD_HOSTS=('subtitlestar.com', 'file-share.io'),
    SUBTITLESTAR_MAX_RESULTS_PER_LOOKUP=3,
)
class SubtitleStarProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_candidate_parser_keeps_only_detail_pages(self):
        html = """
          <a href="/persian-subtitles-example-movie/">دانلود زیرنویس فارسی فیلم Example</a>
          <a href="/years/2024/">سال 2024</a>
          <a href="https://tracker.invalid/file.zip">دانلود تبلیغ</a>
        """
        self.assertEqual(
            _candidate_pages(html, 'https://subtitlestar.com/?s=example'),
            ['https://subtitlestar.com/persian-subtitles-example-movie/'],
        )

    def test_identity_requires_exact_imdb_id(self):
        html = '<a href="https://www.imdb.com/title/tt12345678/">IMDb</a>'
        self.assertTrue(
            _has_exact_identity(html, imdb_id='tt12345678', title='Example', year=2024),
        )
        self.assertFalse(
            _has_exact_identity(html, imdb_id='tt87654321', title='Example', year=2024),
        )

    def test_download_parser_ignores_preconnect_and_reads_data_url(self):
        html = """
          <link rel="preconnect" href="https://file-share.io">
          <button class="download-button"
                  data-url="https://file-share.io/f/opaque-id">دانلود</button>
        """
        self.assertEqual(
            _download_links(html, 'https://subtitlestar.com/example/'),
            ['https://file-share.io/f/opaque-id'],
        )

    def test_zip_rejects_traversal_and_non_persian_members(self):
        persian_srt = (
            '1\n00:00:01,000 --> 00:00:02,000\nسلام، اين يك زيرنويس فارسي است.\n'
        ).encode('windows-1256')
        archive = _zip_payload({
            '../unsafe.srt': persian_srt,
            'Example.Movie.2024.1080p.WEB-DL.Farsi.srt': persian_srt,
            'Example.Movie.2024.English.srt': b'1\n00:00:01,000 --> 00:00:02,000\nEnglish only\n',
        })

        members = _safe_zip_members(archive)

        self.assertEqual(len(members), 1)
        self.assertEqual(members[0][0], 'Example.Movie.2024.1080p.WEB-DL.Farsi.srt')

    def test_lookup_matches_imdb_and_release_to_video(self):
        search = _Response(
            body=b'<a href="/persian-subtitles-example-movie/">Example</a>',
            url='https://subtitlestar.com/?s=tt12345678',
            content_type='text/html',
            filename='',
        )
        detail = _Response(
            body=(
                b'<a href="https://www.imdb.com/title/tt12345678/">IMDb</a>'
                b'<a href="https://file-share.io/download/example.zip">download</a>'
            ),
            url='https://subtitlestar.com/persian-subtitles-example-movie/',
            content_type='text/html',
            filename='',
        )
        persian_srt = (
            '1\n00:00:01,000 --> 00:00:03,000\nسلام دنيا، اين زيرنويس فارسي است.\n'
        ).encode('windows-1256')
        archive = _Response(
            body=_zip_payload({
                'Example.Movie.2024.1080p.BluRay.Farsi.srt': persian_srt,
                'Example.Movie.2024.1080p.WEB-DL.Farsi.srt': persian_srt,
            }),
            url='https://file-share.io/download/example.zip',
            content_type='application/zip',
            filename='Example.Movie.2024.zip',
        )
        movie = SimpleNamespace(
            imdb_id='tt12345678',
            original_title='Example Movie',
            title='فیلم نمونه',
            release_year=2024,
        )
        videos = [
            'https://media.example/Example.Movie.2024.1080p.WEB-DL.x264.mp4',
            'https://media.example/Example.Movie.2024.720p.WEB-DL.x264.mp4',
        ]

        with patch('apps.catalog.subtitle_star._fetch', side_effect=[search, detail, archive]):
            match = find_movie_subtitle(movie, video_urls=videos)

        self.assertIsNotNone(match)
        self.assertIn('WEB-DL', match.filename)
        self.assertEqual(match.imdb_id, 'tt12345678')
        self.assertEqual(match.source_urls, tuple(videos))

    def test_latin_title_hint_from_film2media_path(self):
        url = (
            'https://cdn.example/yA3f/Film/2024/Marco.2024/BluSUB/'
            'Marco.2024.1080p.BluRay.YIFY.Farsi.Sub.Film2Media.mkv'
        )
        self.assertEqual(latin_title_hint_from_urls([url]), 'Marco')
        soft = 'https://cdn.example/Soft/Example.Movie.2024.480p.WEB-DL.Farsi.Sub.mp4'
        self.assertEqual(latin_title_hint_from_urls([soft]), 'Example Movie')
        title, fa = resolve_subtitlestar_search_title(
            original_title='മാർക്കോ',
            display_title='مارکو',
            video_urls=[url],
        )
        self.assertEqual(title, 'Marco')
        self.assertEqual(fa, 'مارکو')

    def test_resolve_drops_accented_colon_tail_for_search(self):
        """TMDB ``Dreams: Sueños`` must search as ``Dreams``, matching SubtitleStar."""
        url = (
            'https://cdn.example/yA3f/Movie/2025/Dreams.2025/SUB/'
            'Dreams.2025.480p.WEB-DL.Farsi.Sub.Film2Media.mkv'
        )
        title, fa = resolve_subtitlestar_search_title(
            original_title='Dreams: Sueños',
            display_title='رویاها',
            video_urls=[url],
        )
        self.assertEqual(title, 'Dreams')
        self.assertEqual(fa, 'رویاها')
        # ASCII colon titles like Spider-Man: No Way Home stay intact.
        sp, _ = resolve_subtitlestar_search_title(
            original_title='Spider-Man: No Way Home',
            display_title='مرد عنکبوتی',
            video_urls=[],
        )
        self.assertEqual(sp, 'Spider-Man: No Way Home')

    def test_search_terms_prefer_cdn_title_year(self):
        from apps.catalog.subtitle_star import _subtitlestar_search_terms

        url = (
            'https://cdn.example/yA3f/Movie/2025/Dreams.2025/SUB/'
            'Dreams.2025.480p.WEB-DL.Farsi.Sub.Film2Media.mkv'
        )
        terms = _subtitlestar_search_terms(
            title='Dreams',
            fa_title='رویاها',
            year=2025,
            imdb_id='tt31710990',
            video_urls=[url],
        )
        self.assertEqual(terms[0], 'Dreams 2025')
        self.assertIn('tt31710990', terms)

    def test_title_match_prefers_exact_dreams_over_train_dreams(self):
        from apps.catalog.subtitle_star import _title_match_ratio

        exact = _title_match_ratio(
            'https://subtitlestar.com/persian-subtitles-dreams-2025/',
            'Dreams',
        )
        train = _title_match_ratio(
            'https://subtitlestar.com/persian-subtitles-train-dreams-2025/',
            'Dreams',
        )
        self.assertGreater(exact, train)

    def test_clean_release_title_keeps_trailing_black(self):
        from apps.catalog.subtitle_star import _clean_release_title, latin_title_hint_from_urls

        self.assertEqual(_clean_release_title('Orange.Is.the.New.Black'), 'Orange Is the New Black')
        url = (
            'https://cdn.example/Series/Orange.Is.the.New.Black/'
            'Orange.Is.the.New.Black.S01E01.1080p.Farsi.Sub.mkv'
        )
        self.assertEqual(latin_title_hint_from_urls([url]), 'Orange Is the New Black')
        title, _ = resolve_subtitlestar_search_title(
            original_title='Orange Is the New Black',
            display_title='نارنجی مد جدید است',
            video_urls=[url],
        )
        self.assertEqual(title, 'Orange Is the New Black')

    def test_download_links_prefer_needed_season_pack(self):
        from apps.catalog.subtitle_star import _download_links_for_seasons

        html = '''
        <a href="https://dl.subtitlestar.com/dlsub/show-All-S07.zip">S07</a>
        <a href="https://dl.subtitlestar.com/dlsub/show-All-S01.zip">S01</a>
        <a href="https://dl.subtitlestar.com/dlsub/show-All-S06.zip">S06</a>
        '''
        links = _download_links_for_seasons(
            html,
            'https://subtitlestar.com/persian-subtitles-show/',
            needed_seasons={1},
        )
        self.assertTrue(links[0].endswith('All-S01.zip'), links[:3])

    def test_lookup_uses_cdn_english_when_original_title_is_non_latin(self):
        """Malayalam/CJK original_title must not poison SubtitleStar ?s= terms."""
        search = _Response(
            body=b'<a href="/persian-subtitles-marco-2024/">Marco</a>',
            url='https://subtitlestar.com/?s=Marco',
            content_type='text/html',
            filename='',
        )
        detail = _Response(
            body=(
                b'<a href="https://www.imdb.com/title/tt29383379/">IMDb</a>'
                b'<a href="https://file-share.io/download/marco.zip">download</a>'
            ),
            url='https://subtitlestar.com/persian-subtitles-marco-2024/',
            content_type='text/html',
            filename='',
        )
        persian_srt = (
            '1\n00:00:01,000 --> 00:00:03,000\nسلام دنيا، اين زيرنويس فارسي است.\n'
        ).encode('utf-8')
        archive = _Response(
            body=_zip_payload({'Marco.2024.WEB-DL.Farsi.srt': persian_srt}),
            url='https://file-share.io/download/marco.zip',
            content_type='application/zip',
            filename='marco.zip',
        )
        movie = SimpleNamespace(
            imdb_id='tt29383379',
            original_title='മാർക്കോ',
            title='مارکو',
            release_year=2024,
        )
        soft = (
            'https://cdn.example/Film/2024/Marco.2024/BluSUB/'
            'Marco.2024.1080p.BluRay.YIFY.Farsi.Sub.Film2Media.mkv'
        )

        with patch('apps.catalog.subtitle_star._fetch', side_effect=[search, detail, archive]):
            match = find_movie_subtitle(movie, video_urls=[soft])

        self.assertIsNotNone(match)
        self.assertIn('Marco', match.filename)
        """Film2Media Soft WEB encode + SubtitleStar BluRay pack still attaches."""
        search = _Response(
            body=b'<a href="/persian-subtitles-example-movie/">Example</a>',
            url='https://subtitlestar.com/?s=tt12345678',
            content_type='text/html',
            filename='',
        )
        detail = _Response(
            body=(
                b'<a href="https://www.imdb.com/title/tt12345678/">IMDb</a>'
                b'<a href="https://file-share.io/download/example.zip">download</a>'
            ),
            url='https://subtitlestar.com/persian-subtitles-example-movie/',
            content_type='text/html',
            filename='',
        )
        persian_srt = (
            '1\n00:00:01,000 --> 00:00:03,000\nسلام دنيا، اين زيرنويس فارسي است.\n'
        ).encode('windows-1256')
        archive = _Response(
            body=_zip_payload({
                'Example.Movie.2024.1080p.BluRay.Farsi.srt': persian_srt,
            }),
            url='https://file-share.io/download/example.zip',
            content_type='application/zip',
            filename='Example.Movie.2024.zip',
        )
        movie = SimpleNamespace(
            imdb_id='tt12345678',
            original_title='Example Movie',
            title='فیلم نمونه',
            release_year=2024,
        )
        soft = 'https://cdn.example/Soft/Example.Movie.2024.480p.WEB-DL.Farsi.Sub.mp4'

        with patch('apps.catalog.subtitle_star._fetch', side_effect=[search, detail, archive]):
            match = find_movie_subtitle(movie, video_urls=[soft])

        self.assertIsNotNone(match)
        self.assertIn('BluRay', match.filename)
        self.assertEqual(match.source_urls, (soft,))

    def test_lookup_rejects_similar_title_with_other_imdb_id(self):
        search = _Response(
            body=b'<a href="/persian-subtitles-example-movie/">Example</a>',
            url='https://subtitlestar.com/?s=tt12345678',
            content_type='text/html',
            filename='',
        )
        wrong_detail = _Response(
            body=b'<a href="https://www.imdb.com/title/tt99999999/">IMDb</a>',
            url='https://subtitlestar.com/persian-subtitles-example-movie/',
            content_type='text/html',
            filename='',
        )
        movie = SimpleNamespace(
            imdb_id='tt12345678',
            original_title='Example Movie',
            title='Example Movie',
            release_year=2024,
        )

        with patch('apps.catalog.subtitle_star._fetch', side_effect=[search, wrong_detail]):
            match = find_movie_subtitle(
                movie,
                video_urls=['https://media.example/Example.Movie.2024.WEB-DL.mp4'],
            )

        self.assertIsNone(match)

    def test_episode_key_parser(self):
        self.assertEqual(episode_key_from_name('Show.S01E05.WEB-DL.Farsi.srt'), (1, 5))
        self.assertEqual(episode_key_from_name('Show.1x05.720p.srt'), (1, 5))
        self.assertEqual(
            episode_key_from_name('Season.02/Show.E03.Farsi.srt'),
            (2, 3),
        )

    def test_series_lookup_splits_zip_by_episode(self):
        search = _Response(
            body=b'<a href="/persian-subtitles-example-series/">Example</a>',
            url='https://subtitlestar.com/?s=tt12345678',
            content_type='text/html',
            filename='',
        )
        detail = _Response(
            body=(
                b'<a href="https://www.imdb.com/title/tt12345678/">IMDb</a>'
                b'<a href="https://file-share.io/download/example-s01.zip">download</a>'
            ),
            url='https://subtitlestar.com/persian-subtitles-example-series/',
            content_type='text/html',
            filename='',
        )
        persian_srt = (
            '1\n00:00:01,000 --> 00:00:03,000\nسلام دنيا، اين زيرنويس فارسي است.\n'
        ).encode('windows-1256')
        archive = _Response(
            body=_zip_payload({
                'Example.S01E01.1080p.WEB-DL.Farsi.srt': persian_srt,
                'Example.S01E02.1080p.WEB-DL.Farsi.srt': persian_srt,
                'Example.S01E03.1080p.WEB-DL.Farsi.srt': persian_srt,
            }),
            url='https://file-share.io/download/example-s01.zip',
            content_type='application/zip',
            filename='Example.S01.zip',
        )
        series = SimpleNamespace(
            imdb_id='tt12345678',
            original_title='Example Series',
            title='سریال نمونه',
            start_year=2024,
        )
        episode_videos = {
            (1, 1): ['https://media.example/Example.S01E01.1080p.WEB-DL.mp4'],
            (1, 2): ['https://media.example/Example.S01E02.1080p.WEB-DL.mp4'],
        }

        with patch('apps.catalog.subtitle_star._fetch', side_effect=[search, detail, archive]):
            matches = find_series_episode_subtitles(series, episode_videos=episode_videos)

        self.assertEqual(len(matches), 2)
        self.assertEqual(
            {(item.season_number, item.episode_number) for item in matches},
            {(1, 1), (1, 2)},
        )
        self.assertTrue(all(item.imdb_id == 'tt12345678' for item in matches))

    def test_series_lookup_stops_after_first_complete_season_pack(self):
        search = _Response(
            body=b'<a href="/persian-subtitles-example-series/">Example</a>',
            url='https://subtitlestar.com/?s=Example',
            content_type='text/html',
            filename='',
        )
        detail = _Response(
            body=(
                b'<a href="https://www.imdb.com/title/tt12345678/">IMDb</a>'
                b'<a href="https://file-share.io/example-All-S01.zip">S01</a>'
                b'<a href="https://file-share.io/example-All-S02.zip">S02</a>'
            ),
            url='https://subtitlestar.com/persian-subtitles-example-series/',
            content_type='text/html',
            filename='',
        )
        persian_srt = (
            '1\n00:00:01,000 --> 00:00:03,000\nسلام دنیا، این زیرنویس فارسی است.\n'
        ).encode('utf-8')
        first_archive = _Response(
            body=_zip_payload({'Example.S01E01.WEB-DL.Farsi.srt': persian_srt}),
            url='https://file-share.io/example-All-S01.zip',
            content_type='application/zip',
            filename='example-All-S01.zip',
        )
        series = SimpleNamespace(
            imdb_id='tt12345678', original_title='Example Series',
            title='سریال نمونه', start_year=2024,
        )
        fetches = [search, detail, first_archive]
        with patch('apps.catalog.subtitle_star._fetch', side_effect=fetches) as fetch:
            matches = find_series_episode_subtitles(
                series,
                episode_videos={(1, 1): ['https://media.example/Example.S01E01.WEB-DL.mp4']},
            )

        self.assertEqual(len(matches), 1)
        self.assertEqual(fetch.call_count, 3)


class SubtitleStarPlaybackIntegrationTests(SimpleTestCase):
    def test_attach_saves_webvtt_and_binds_compatible_sources(self):
        from apps.catalog.subtitle_extract import _attach_subtitlestar_subtitle

        first = 'https://media.example/Example.Movie.2024.1080p.WEB-DL.mp4'
        second = 'https://media.example/Example.Movie.2024.720p.WEB-DL.mp4'
        raw = (
            '1\n00:00:01,000 --> 00:00:03,000\nسلام دنيا، اين زيرنويس فارسي است.\n'
        ).encode('windows-1256')
        match = SubtitleStarMatch(
            payload=raw,
            filename='Example.Movie.2024.WEB-DL.Farsi.srt',
            page_url='https://subtitlestar.com/persian-subtitles-example-movie/',
            download_url='https://file-share.io/download/example.zip',
            release_name='Example.Movie.2024.WEB-DL.Farsi.srt',
            source_urls=(first, second),
            imdb_id='tt12345678',
        )
        movie = SimpleNamespace(
            pk=12,
            tmdb_id=34,
            subtitle_tracks=[],
            has_subtitle=False,
            save=lambda **kwargs: None,
        )
        links = [
            {'url': first, 'quality': '1080p', 'kind': 'movie'},
            {'url': second, 'quality': '720p', 'kind': 'movie'},
        ]

        with patch('apps.catalog.subtitle_star.find_movie_subtitle', return_value=match), \
             patch('apps.catalog.subtitle_extract._store_webvtt', return_value='catalog/subtitles/example.vtt'):
            changed = _attach_subtitlestar_subtitle(movie, links, timeout_seconds=30)

        self.assertTrue(changed)
        self.assertTrue(movie.has_subtitle)
        self.assertEqual(len(movie.subtitle_tracks), 2)
        self.assertEqual(movie.subtitle_tracks[0]['source_url'], first)
        self.assertEqual(movie.subtitle_tracks[0]['provider'], 'subtitlestar')
        self.assertEqual(movie.subtitle_tracks[0]['source_priority'], 2)
        self.assertEqual(movie.subtitle_tracks[0]['sync_confidence'], 'release-match')

    def test_attach_series_binds_episode_tracks(self):
        from apps.catalog.subtitle_extract import _attach_subtitlestar_series
        from apps.catalog.subtitle_star import SubtitleStarEpisodeMatch

        video = 'https://media.example/Example.S01E01.1080p.WEB-DL.mp4'
        raw = (
            '1\n00:00:01,000 --> 00:00:03,000\nسلام دنيا، اين زيرنويس فارسي است.\n'
        ).encode('windows-1256')
        match = SubtitleStarEpisodeMatch(
            season_number=1,
            episode_number=1,
            payload=raw,
            filename='Example.S01E01.WEB-DL.Farsi.srt',
            page_url='https://subtitlestar.com/persian-subtitles-example-series/',
            download_url='https://file-share.io/download/example.zip',
            release_name='Example.S01E01.WEB-DL.Farsi.srt',
            source_urls=(video,),
            imdb_id='tt12345678',
        )
        series = SimpleNamespace(
            pk=9,
            imdb_id='tt12345678',
            original_title='Example Series',
            title='سریال نمونه',
            start_year=2024,
            download_links=[{
                'url': video,
                'quality': '1080p',
                'kind': 'hardsub',
                'season_number': 1,
                'episode_number': 1,
            }],
        )
        episode = SimpleNamespace(
            pk=1,
            episode_number=1,
            subtitle_tracks=[],
            season=SimpleNamespace(season_number=1, series_id=9),
            video_url=video,
            save=lambda **kwargs: None,
        )
        qs = SimpleNamespace(
            select_related=lambda *args: SimpleNamespace(first=lambda: episode),
        )

        with patch('apps.catalog.models.Episode') as EpisodeModel, \
             patch(
                 'apps.catalog.subtitle_extract._episode_video_map',
                 return_value={(1, 1): [video]},
             ), \
             patch('apps.catalog.subtitle_star.find_series_episode_subtitles', return_value=[match]), \
             patch('apps.catalog.subtitle_extract._store_webvtt', return_value='catalog/subtitles/s01e01.vtt'), \
             patch('apps.catalog.subtitle_extract.normalize_imdb_id_safe', return_value='tt12345678'):
            EpisodeModel.objects.filter.return_value = qs
            result = _attach_subtitlestar_series(
                series,
                series.download_links,
                timeout_seconds=30,
            )

        self.assertEqual(result['attached'], 1)
        self.assertEqual(episode.subtitle_tracks[0]['provider'], 'subtitlestar')
        self.assertEqual(episode.subtitle_tracks[0]['source_url'], video)
        self.assertEqual(episode.subtitle_tracks[0]['source_priority'], 2)
