"""Unit tests for SoftSub helpers (no DB required for pure classifiers)."""

from django.test import SimpleTestCase, TestCase

from apps.catalog.subtitle_extract import (
    _pick_extract_source,
    _pick_subtitle_stream,
    _prioritize_extract_sources,
    _is_usable_persian_webvtt,
    _non_conflicting_release_sources,
    _season_episode_key,
    _strict_release_sources,
    ass_to_webvtt,
    download_links_imply_softsub,
    looks_like_dub_link,
    looks_like_softsub_link,
    normalize_subtitle_payload,
    srt_to_webvtt,
)


class SoftSubClassifierTests(SimpleTestCase):
    def test_softsub_and_dub_detection(self):
        soft = {'label': '720 SoftSub', 'url': 'https://cdn.example/a.mkv', 'kind': 'softsub'}
        dub = {'label': 'دوبله فارسی 1080', 'url': 'https://cdn.example/b.mp4', 'kind': 'dubbed'}
        vtt = {'label': 'فارسی', 'url': 'https://cdn.example/fa.vtt', 'kind': 'subtitle'}
        # SoftSub encodes are often labeled «زیرنویس چسبیده» on provider pages.
        soft_path = {
            'label': 'زیرنویس چسبیده · BluRay 720p',
            'url': 'https://dl.example/Movies/x/Soft/Movie.720p.mkv',
            'kind': 'subtitle',
        }
        farsi_sub = {
            'label': 'قسمت 1 · BluRay 1080p',
            'url': 'https://cdn.example/Series/The.Wire.S03E01.1080p.Farsi.Sub.Film2Media.mkv',
            'kind': 'subtitle',
        }
        # Provider hardsub tag + bare Farsi.Sub (no Soft/ folder) = burned-in, not Soft.
        hard_farsi = {
            'label': 'زیرنویس فارسی · WEB-DL 1080p',
            'url': 'https://cdn.example/Movie/2025/X/X.1080p.WEB-DL.Farsi.Sub.Film2Media.mkv',
            'kind': 'hardsub',
            'subtitle_type': 'hard',
        }
        blusub = {
            'label': 'زیرنویس چسبیده · BluRay 720p',
            'url': 'https://cdn.abrtech.top/yA3f/Movie/2025/X/BluSUB/X.720p.Farsi.Sub.Film2Media.mkv',
            'kind': 'hardsub',
        }

        self.assertTrue(looks_like_softsub_link(soft))
        self.assertTrue(looks_like_softsub_link(vtt))
        self.assertTrue(looks_like_softsub_link(soft_path))
        self.assertTrue(looks_like_softsub_link(farsi_sub))
        self.assertTrue(looks_like_softsub_link(blusub))
        self.assertFalse(looks_like_softsub_link(dub))
        self.assertFalse(looks_like_softsub_link(hard_farsi))
        from apps.catalog.subtitle_extract import looks_like_hardsub_link
        self.assertTrue(looks_like_hardsub_link(hard_farsi))
        self.assertTrue(looks_like_dub_link(dub))
        self.assertTrue(download_links_imply_softsub([soft, dub]))
        self.assertTrue(download_links_imply_softsub([soft_path]))
        self.assertTrue(download_links_imply_softsub([farsi_sub]))

    def test_classify_prefers_cdn_softsub_over_chasbide_heading(self):
        from apps.catalog.subtitle_extract import canonicalize_download_link, classify_download_link_kind

        kind, subtitle_type = classify_download_link_kind(
            'https://s8.dlyar.top/Movies/2026/X/Soft/X.2026.1080p.SoftSub.mp4',
            surrounding='زیرنویس چسبیده',
            section_kind='hardsub',
        )
        self.assertEqual((kind, subtitle_type), ('softsub', 'soft'))

        # Real Dornatv pattern: SoftSub filename under «چسبیده» box head.
        soft_mislabel = canonicalize_download_link({
            'label': 'زیرنویس فارسی · 1080p',
            'kind': 'hardsub',
            'section_kind': 'hardsub',
            'url': (
                'https://s8.dlyar.top/Movies/2026/08/X/'
                'Gli.Occhi.Degli.Altri.2025.ITA.WEB-DL.1080p.WEBRip.x264.AAC-YTS.SoftSub.mp4'
            ),
        })
        self.assertEqual(soft_mislabel['kind'], 'softsub')
        self.assertTrue(str(soft_mislabel['quality']).startswith('1080p'))
        self.assertIn('زیرنویس نرم', soft_mislabel['label'])

        # Dornatv dub spelling «Duble».
        duble = canonicalize_download_link({
            'label': 'دوبله فارسی · 1080p',
            'kind': 'hardsub',
            'section_kind': 'dubbed',
            'url': 'https://cdn.example/Movies/Satluj.2026.1080p.WEB.DL.Duble.mp4',
        })
        self.assertEqual(duble['kind'], 'dubbed')
        self.assertIn('دوبله فارسی', duble['label'])

        hard = canonicalize_download_link({
            'label': 'زیرنویس فارسی · 1080p',
            'kind': 'hardsub',
            'url': 'https://cdn.example/Movie/X/X.1080p.WEBDL.HardSub.mkv',
        })
        self.assertEqual(hard['kind'], 'hardsub')
        self.assertIn('زیرنویس چسبیده', hard['label'])

        plain = classify_download_link_kind('https://cdn.example/Movies/X.1080p.mkv')
        self.assertEqual(plain, ('video', ''))

    def test_quality_keeps_540p_and_codec_from_filename(self):
        from apps.catalog.subtitle_extract import canonicalize_download_link

        row = canonicalize_download_link({
            'url': 'https://cdn.example/Series/Show.E001.HardSub.540p.mkv',
            'kind': 'hardsub',
            'label': 'دانلود',
        })
        self.assertEqual(row['quality'], '540p')
        self.assertEqual(row['kind'], 'hardsub')

    def test_coalesce_reclassifies_mislabeled_softsub(self):
        from apps.catalog.subtitle_extract import coalesce_download_links

        existing = [{
            'label': 'زیرنویس فارسی · 1080p',
            'kind': 'hardsub',
            'url': 'https://cdn.example/Soft/a.mkv?sig=old',
        }]
        incoming = [{
            'label': 'زیرنویس چسبیده · 1080p',
            'kind': 'hardsub',
            'url': 'https://cdn.example/Soft/a.mkv?sig=new',
        }]
        merged = coalesce_download_links(existing, incoming, replace=True)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['kind'], 'softsub')
        self.assertIn('sig=new', merged[0]['url'])

    def test_coalesce_preserves_softsub_when_replace_lacks_soft(self):
        from apps.catalog.subtitle_extract import coalesce_download_links

        existing = [
            {'label': 'Soft 720', 'url': 'https://cdn.example/Soft/a.mkv', 'kind': 'subtitle'},
            {'label': 'Dub', 'url': 'https://cdn.example/Dubbed/a.mkv', 'kind': 'dubbed'},
        ]
        incoming = [
            {'label': 'Hardsub', 'url': 'https://cdn.example/Hard/a.mkv', 'kind': 'hardsub'},
            {'label': 'Dub', 'url': 'https://cdn.example/Dubbed/b.mkv', 'kind': 'dubbed'},
        ]
        merged = coalesce_download_links(existing, incoming, replace=True)
        self.assertTrue(download_links_imply_softsub(merged))
        self.assertTrue(any('/Soft/' in str(item.get('url') or '') for item in merged))
        # Prior dub encode + new dub path both kept; hardsub added.
        self.assertEqual(len(merged), 4)

    def test_coalesce_refresh_same_path_uses_incoming_url(self):
        from apps.catalog.subtitle_extract import coalesce_download_links

        existing = [{'label': 'Old Soft', 'url': 'https://cdn.example/Soft/a.mkv?sig=old', 'kind': 'subtitle'}]
        incoming = [{'label': 'New Soft', 'url': 'https://cdn.example/Soft/a.mkv?sig=new', 'kind': 'softsub'}]
        merged = coalesce_download_links(existing, incoming, replace=True)
        self.assertEqual(len(merged), 1)
        self.assertIn('sig=new', merged[0]['url'])
        self.assertEqual(merged[0]['kind'], 'softsub')

    def test_coalesce_prunes_known_dead_and_malformed_existing_urls(self):
        from apps.catalog.subtitle_extract import coalesce_download_links

        existing = [
            {'url': 'https://dl5.cdnhost.lol/Movies/a.mkv', 'kind': 'softsub'},
            {'url': 'https://cdn.example/Show.E01.mp41', 'kind': 'hardsub'},
        ]
        incoming = [
            {'url': 'https://cdn.example/Show.E01.mp4', 'kind': 'hardsub'},
        ]
        merged = coalesce_download_links(existing, incoming, replace=True)
        self.assertEqual([row['url'] for row in merged], ['https://cdn.example/Show.E01.mp4'])

    def test_coalesce_unions_all_qualities_and_kinds(self):
        from apps.catalog.subtitle_extract import coalesce_download_links

        existing = [
            {'url': 'https://cdn.example/Dubbed/720.mkv', 'kind': 'dubbed', 'quality': '720p'},
            {'url': 'https://cdn.example/Soft/1080.mkv', 'kind': 'softsub', 'quality': '1080p'},
        ]
        incoming = [
            {'url': 'https://cdn.example/Dubbed/1080.mkv', 'kind': 'dubbed', 'quality': '1080p'},
            {'url': 'https://cdn.example/Hard/720.mkv', 'kind': 'hardsub', 'quality': '720p'},
            {'url': 'https://cdn.example/Soft/480.mkv', 'kind': 'softsub', 'quality': '480p'},
        ]
        merged = coalesce_download_links(existing, incoming, replace=True)
        self.assertEqual(len(merged), 5)
        qualities = {item['quality'] for item in merged}
        self.assertEqual(qualities, {'720p', '1080p', '480p'})
        kinds = {item['kind'] for item in merged}
        self.assertEqual(kinds, {'dubbed', 'softsub', 'hardsub'})

    def test_pick_prefers_standalone_vtt_then_720(self):
        links = [
            {'label': '1080 SoftSub', 'url': 'https://cdn.example/a-1080.mkv', 'kind': 'softsub', 'quality': '1080p'},
            {'label': '720 SoftSub', 'url': 'https://cdn.example/a-720.mp4', 'kind': 'softsub', 'quality': '720p'},
            {'label': 'VTT', 'url': 'https://cdn.example/fa.vtt', 'kind': 'subtitle', 'quality': ''},
        ]
        picked = _pick_extract_source(links)
        self.assertEqual(picked['url'], 'https://cdn.example/fa.vtt')

    def test_pick_prefers_480p_soft_over_720_for_extract_speed(self):
        links = [
            {'label': '1080 SoftSub', 'url': 'https://cdn.example/a-1080.mkv', 'kind': 'softsub', 'quality': '1080p'},
            {'label': '720 SoftSub', 'url': 'https://cdn.example/a-720.mkv', 'kind': 'softsub', 'quality': '720p'},
            {'label': '480 SoftSub', 'url': 'https://cdn.example/a-480.mp4', 'kind': 'softsub', 'quality': '480p'},
        ]
        picked = _pick_extract_source(links)
        self.assertEqual(picked['url'], 'https://cdn.example/a-480.mp4')

    def test_current_playback_source_overrides_extract_quality_ranking(self):
        sources = [
            {'url': 'https://cdn.example/a-480.mp4?token=fresh', 'kind': 'softsub'},
            {'url': 'https://cdn.example/a-1080.mkv?token=new', 'kind': 'softsub'},
        ]
        prioritized = _prioritize_extract_sources(
            sources,
            'https://cdn.example/a-1080.mkv?token=from-player',
        )
        self.assertIn('a-1080.mkv', prioritized[0]['url'])

    def test_ranked_sources_skip_known_dead_soft_hosts(self):
        from apps.catalog.subtitle_extract import _ranked_extract_sources

        links = [
            {
                'label': 'Dead Soft 720',
                'url': 'https://dl4.cdnhost.lol/Series/X/Soft/720p/Show.S01E01.720p.mkv',
                'kind': 'softsub',
                'quality': '720p',
            },
            {
                'label': 'Live SoftSub',
                'url': 'https://zz.abrtech.top/oG4i/Series/Show.S01E01.720p.SoftSub.Film2Media.mkv',
                'kind': 'softsub',
                'quality': '720p',
            },
        ]
        ranked = _ranked_extract_sources(links)
        self.assertEqual(len(ranked), 1)
        self.assertIn('abrtech.top', ranked[0]['url'])

    def test_season_episode_key_from_meta_and_label(self):
        self.assertEqual(
            _season_episode_key({'season_number': 2, 'episode_number': 5}),
            (2, 5),
        )
        self.assertEqual(
            _season_episode_key({'label': 'فصل 1 قسمت 3 SoftSub 720'}),
            (1, 3),
        )

    def test_srt_to_webvtt_strips_html_and_normalizes_timing(self):
        srt = (
            "1\n"
            "00:00:05,000 --> 00:00:08,500\n"
            "<font color=\"#ffc13c\">سلام دنیا</font>\n\n"
            "2\n"
            "00:01:00,100 --> 00:01:02,200\n"
            "خط دوم\n"
        )
        vtt = srt_to_webvtt(srt)
        self.assertIn('WEBVTT', vtt)
        self.assertIn('00:00:05.000 --> 00:00:08.500', vtt)
        self.assertIn('سلام دنیا', vtt)
        self.assertNotIn('<font', vtt)
        self.assertIn('00:01:00.100 --> 00:01:02.200', vtt)

    def test_ass_to_webvtt_dialogue_lines(self):
        ass = (
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,,سلام{\\i1}دنیا{\\i0}\n"
        )
        vtt = ass_to_webvtt(ass)
        self.assertIn('00:00:01.000 --> 00:00:03.500', vtt)
        self.assertIn('سلامدنیا', vtt)

    def test_normalize_payload_detects_srt_without_extension(self):
        payload = b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"
        out = normalize_subtitle_payload(payload, filename='track.bin')
        self.assertIsNotNone(out)
        self.assertIn(b'WEBVTT', out)
        self.assertIn(b'Hi', out)

    def test_normalize_payload_decodes_windows_1256_persian(self):
        payload = (
            '1\n00:00:01,000 --> 00:00:02,000\nسلام دنيا\n'
        ).encode('windows-1256')
        out = normalize_subtitle_payload(payload, filename='track.srt')
        self.assertIsNotNone(out)
        self.assertIn('سلام دنیا', out.decode('utf-8'))

    def test_persian_webvtt_validation_rejects_english_or_malformed_tracks(self):
        valid = (
            'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n'
            'این یک زیرنویس فارسی هماهنگ و معتبر است\n'
        ).encode()
        english = b'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nEnglish only\n'
        malformed = 'WEBVTT\n\nمتن فارسی بدون زمان‌بندی معتبر'.encode()
        self.assertTrue(_is_usable_persian_webvtt(valid))
        self.assertFalse(_is_usable_persian_webvtt(english))
        self.assertFalse(_is_usable_persian_webvtt(malformed))

    def test_provider_release_binding_rejects_known_source_or_fps_conflicts(self):
        subtitle_release = 'Example.Movie.2024.BluRay.24fps.Persian.srt'
        matching = 'https://cdn.example/Example.Movie.2024.1080p.BluRay.24fps.mkv'
        wrong_source = 'https://cdn.example/Example.Movie.2024.1080p.WEB-DL.24fps.mkv'
        wrong_fps = 'https://cdn.example/Example.Movie.2024.1080p.BluRay.25fps.mkv'

        self.assertEqual(
            _strict_release_sources(subtitle_release, [wrong_source, wrong_fps, matching]),
            [matching],
        )
        self.assertEqual(
            _non_conflicting_release_sources(subtitle_release, [wrong_source, wrong_fps]),
            [],
        )

    def test_movie_pipeline_uses_embedded_before_provider_fallbacks(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from apps.catalog.subtitle_extract import attach_extracted_subtitle

        movie = SimpleNamespace(
            pk=7,
            subtitle_tracks=[],
            has_subtitle=False,
            download_links=[
                {'url': 'https://cdn.example/Soft/movie.mkv', 'kind': 'softsub'},
                {'url': 'https://cdn.example/Hard/movie.mkv', 'kind': 'hardsub'},
            ],
        )
        with patch(
            'apps.catalog.subtitle_extract._attach_ffmpeg_softsub_movie',
            return_value=True,
        ) as embedded, patch(
            'apps.catalog.subtitle_extract._attach_subtitlestar_subtitle',
        ) as star, patch(
            'apps.catalog.subtitle_extract._attach_subzone_subtitle',
        ) as subzone:
            changed = attach_extracted_subtitle(
                movie,
                force=True,
                allow_ffmpeg=True,
                prefer_embedded=True,
                preferred_source_url='https://cdn.example/Soft/movie.mkv',
            )

        self.assertTrue(changed)
        self.assertEqual(
            embedded.call_args.kwargs.get('preferred_source_url'),
            'https://cdn.example/Soft/movie.mkv',
        )
        star.assert_not_called()
        subzone.assert_not_called()

    def test_embedded_track_records_exact_source_priority(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from apps.catalog.subtitle_extract import _save_movie_softsub_track

        movie = SimpleNamespace(
            pk=8,
            tmdb_id=88,
            download_links=[],
            subtitle_tracks=[],
            has_subtitle=False,
            save=lambda **kwargs: None,
        )
        payload = (
            'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n'
            'این زیرنویس فارسی از فایل اصلی استخراج شده است\n'
        ).encode()
        with patch(
            'apps.catalog.subtitle_extract._store_webvtt',
            return_value='catalog/subtitles/exact.vtt',
        ):
            changed = _save_movie_softsub_track(
                movie,
                payload,
                source_url='https://cdn.example/Soft/movie.mkv',
                provider='softsub-ffmpeg',
            )

        self.assertTrue(changed)
        self.assertEqual(movie.subtitle_tracks[0]['source_priority'], 1)
        self.assertEqual(movie.subtitle_tracks[0]['sync_confidence'], 'exact-source')

    def test_pick_subtitle_stream_prefers_persian_text(self):
        streams = [
            {'index': 2, 'codec': 'subrip', 'language': 'eng', 'title': ''},
            {'index': 3, 'codec': 'subrip', 'language': 'per', 'title': 'Film2Media'},
            {'index': 4, 'codec': 'hdmv_pgs_subtitle', 'language': 'fas', 'title': ''},
        ]
        picked = _pick_subtitle_stream(streams)
        self.assertEqual(picked['index'], 3)

    def test_extract_skips_mislabeled_english_stream_and_uses_persian(self):
        from unittest.mock import patch

        from apps.catalog.subtitle_extract import extract_webvtt_from_url

        english = b'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nEnglish only\n'
        persian = (
            'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n'
            'این زیرنویس فارسی درست از ترک دوم انتخاب شد\n'
        ).encode()
        streams = [
            {'index': 2, 'codec': 'subrip', 'language': 'und', 'title': ''},
            {'index': 3, 'codec': 'subrip', 'language': 'und', 'title': ''},
        ]
        with patch('apps.catalog.subtitle_extract.ffmpeg_available', return_value=True), patch(
            'apps.catalog.subtitle_extract._ffprobe_subtitle_streams',
            return_value=streams,
        ), patch(
            'apps.catalog.subtitle_extract._ffmpeg_copy_subtitle_stream',
            side_effect=[english, persian],
        ) as extract:
            result = extract_webvtt_from_url('https://cdn.example/Soft/movie.mkv')

        self.assertEqual(result, persian)
        self.assertEqual(extract.call_count, 2)

    def test_series_softsub_save_skips_missing_subtitle_tracks_field(self):
        """Series has no subtitle_tracks column; save must only touch real fields."""
        from unittest.mock import MagicMock, patch

        from apps.catalog.subtitle_extract import attach_series_softsub_tracks

        series = MagicMock()
        series.pk = 42
        series.imdb_id = 'tt1234567'
        series.original_title = 'Example Series'
        series.start_year = 2024
        series.download_links = [{
            'label': 'S01E01 SoftSub 720p',
            'url': 'https://cdn.example/Soft/from-s01e01.mkv',
            'kind': 'softsub',
            'quality': '720p',
            'season_number': 1,
            'episode_number': 1,
        }]
        series.has_subtitle = False

        with patch('apps.catalog.subtitle_extract.ensure_episodes_from_download_links', return_value=0), \
             patch('apps.catalog.subtitle_extract._attach_subtitlestar_series', return_value={'attached': 1, 'matches': 1}), \
             patch('apps.catalog.subtitle_extract.apply_availability_flags', return_value=['has_subtitle']) as flags, \
             patch('apps.catalog.models.Episode') as EpisodeModel:
            qs = MagicMock()
            qs.exclude.return_value.exclude.return_value.exists.return_value = True
            EpisodeModel.objects.filter.return_value = qs
            series.has_subtitle = True
            flags.return_value = ['has_subtitle']

            result = attach_series_softsub_tracks(series, timeout_seconds=5, limit=2)

        self.assertEqual(result['extracted'], 1)
        kwargs = series.save.call_args.kwargs
        self.assertNotIn('subtitle_tracks', kwargs.get('update_fields', []))
        self.assertFalse(hasattr(series, 'subtitle_tracks') and 'subtitle_tracks' in str(series.method_calls))

    def test_is_sidecar_subtitle_url(self):
        from apps.catalog.subtitle_extract import _is_sidecar_subtitle_url

        self.assertTrue(_is_sidecar_subtitle_url('https://cdn.example/a.fa.vtt'))
        self.assertTrue(_is_sidecar_subtitle_url('https://cdn.example/a.srt'))
        self.assertFalse(_is_sidecar_subtitle_url('https://cdn.example/a.mp4'))

    def test_pair_video_source_for_sidecar_subtitle_prefers_stem_match(self):
        from apps.catalog.subtitle_extract import (
            _pair_video_source_for_sidecar_subtitle,
            _prefer_movie_stream_url,
        )

        subtitle_url = 'https://cdn.example/movie/E01.fa.vtt'
        links = [
            {'label': 'فارسی', 'url': subtitle_url, 'kind': 'subtitle'},
            {'label': 'Soft 720', 'url': 'https://cdn.example/movie/E01.mp4', 'kind': 'softsub', 'quality': '720p'},
        ]

        paired = _pair_video_source_for_sidecar_subtitle(
            subtitle_url,
            links,
            fallback_prefer_fn=_prefer_movie_stream_url,
        )
        self.assertEqual(paired, 'https://cdn.example/movie/E01.mp4')

    def test_pair_video_source_for_sidecar_subtitle_falls_back_to_prefer_fn(self):
        from apps.catalog.subtitle_extract import (
            _pair_video_source_for_sidecar_subtitle,
            _prefer_movie_stream_url,
        )

        subtitle_url = 'https://cdn.example/movie/EP1-persian.vtt'
        links = [
            {'label': 'فارسی', 'url': subtitle_url, 'kind': 'subtitle'},
            {'label': 'Dub 1080', 'url': 'https://cdn.example/movie/EP1-dub.mp4', 'kind': 'dubbed', 'quality': '1080p'},
            {'label': 'Original 720', 'url': 'https://cdn.example/movie/EP1-original.mp4', 'kind': 'movie', 'quality': '720p'},
        ]

        paired = _pair_video_source_for_sidecar_subtitle(
            subtitle_url,
            links,
            fallback_prefer_fn=_prefer_movie_stream_url,
        )
        self.assertEqual(paired, 'https://cdn.example/movie/EP1-dub.mp4')

    def test_ensure_reachable_never_returns_dead_cdnhost(self):
        from unittest.mock import MagicMock, patch

        from apps.catalog.subtitle_extract import _ensure_reachable_softsub_sources

        movie = MagicMock()
        movie.download_links = [{
            'label': 'Soft 720',
            'url': 'https://dl5.cdnhost.lol/Movies/x/Soft/a.mkv',
            'kind': 'softsub',
            'quality': '720p',
        }]
        movie.refresh_from_db = MagicMock()

        with patch('apps.catalog.subtitle_extract.refresh_softsub_download_links', return_value=False):
            sources = _ensure_reachable_softsub_sources(movie)
        self.assertEqual(sources, [])

    def test_extract_webvtt_skips_dead_cdnhost(self):
        from apps.catalog.subtitle_extract import extract_webvtt_from_url

        self.assertIsNone(
            extract_webvtt_from_url(
                'https://dl5.cdnhost.lol/Movies/x/Soft/a.mkv?md5=dead&expires=1',
            ),
        )


class SoftSubEpisodeMaterializeTests(TestCase):
    def test_ensure_episodes_skips_rows_without_playable_url(self):
        from apps.catalog.models import Episode, Season, Series
        from apps.catalog.subtitle_extract import ensure_episodes_from_download_links

        series = Series.objects.create(
            title='Stub Guard',
            slug='stub-guard',
            is_published=True,
            download_links=[
                {
                    'label': 'Missing URL',
                    'season_number': 1,
                    'episode_number': 1,
                    'kind': 'softsub',
                    'quality': '720p',
                },
                {
                    'label': 'Playable',
                    'url': 'https://cdn.example/show.S01E02.720p.mkv',
                    'season_number': 1,
                    'episode_number': 2,
                    'kind': 'softsub',
                    'quality': '720p',
                },
            ],
        )
        created = ensure_episodes_from_download_links(series)
        self.assertEqual(created, 1)
        self.assertEqual(Season.objects.filter(series=series).count(), 1)
        self.assertEqual(
            list(
                Episode.objects.filter(season__series=series)
                .order_by('episode_number')
                .values_list('episode_number', 'video_url')
            ),
            [(2, 'https://cdn.example/show.S01E02.720p.mkv')],
        )

    def test_ensure_episodes_keeps_multi_quality_and_backfills_from_url(self):
        from apps.catalog.models import Episode, Series
        from apps.catalog.subtitle_extract import ensure_episodes_from_download_links

        series = Series.objects.create(
            title='Multi Qual',
            slug='multi-qual',
            is_published=True,
            download_links=[
                {
                    'label': '720p',
                    'url': 'https://cdn.example/Show.S01E01.720p.SoftSub.mkv',
                    'kind': 'softsub',
                    'quality': '720p',
                },
                {
                    'label': '1080p',
                    'url': 'https://cdn.example/Show.S01E01.1080p.SoftSub.mkv',
                    'kind': 'softsub',
                    'quality': '1080p',
                },
            ],
        )
        created = ensure_episodes_from_download_links(series)
        self.assertEqual(created, 1)
        episode = Episode.objects.get(season__series=series, episode_number=1)
        self.assertTrue(episode.video_url.startswith('https://'))
        # Both qualities remain on the series JSON SoT.
        self.assertEqual(len(series.download_links), 2)
        # Re-crawl with same URLs should not thrash video_url when previous still in pool.
        previous = episode.video_url
        ensure_episodes_from_download_links(series)
        episode.refresh_from_db()
        self.assertEqual(episode.video_url, previous)
