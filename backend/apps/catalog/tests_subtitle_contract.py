from django.test import SimpleTestCase

from apps.catalog.subtitle_contract import (
    normalize_subtitle_track,
    normalize_subtitle_tracks,
    publicize_subtitle_tracks,
    track_has_playable_cues,
)


class SubtitleContractTests(SimpleTestCase):
    def test_normalize_keeps_relative_key(self):
        row = normalize_subtitle_track({
            'id': 'fa-1',
            'key': 'catalog/subtitles/demo.vtt',
            'label': 'فارسی',
            'language': 'fa',
            'source_url': 'https://cdn.example/Soft/demo.mkv',
            'provider': 'subtitlestar',
            'source_priority': 2,
            'sync_confidence': 'release-match',
            'default': True,
        })
        self.assertEqual(row['key'], 'catalog/subtitles/demo.vtt')
        self.assertEqual(row['provider'], 'subtitlestar')
        self.assertEqual(row['source_priority'], 2)
        self.assertEqual(row['sync_confidence'], 'release-match')
        self.assertNotIn('src', row)

    def test_normalize_dedupes_ids(self):
        tracks = normalize_subtitle_tracks([
            {'id': 'fa', 'key': 'catalog/subtitles/a.vtt'},
            {'id': 'fa', 'key': 'catalog/subtitles/b.vtt'},
        ])
        self.assertEqual(tracks[0]['id'], 'fa')
        self.assertEqual(tracks[1]['id'], 'fa-2')

    def test_publicize_mints_src(self):
        public = publicize_subtitle_tracks([
            {'id': 'fa', 'key': 'catalog/subtitles/a.vtt', 'language': 'fa'},
        ])
        self.assertEqual(len(public), 1)
        self.assertTrue(public[0]['src'])
        self.assertNotIn('key', public[0])

    def test_playable_cues(self):
        self.assertTrue(track_has_playable_cues([{'key': 'catalog/subtitles/a.vtt'}]))
        self.assertFalse(track_has_playable_cues([{'label': 'فارسی'}]))
