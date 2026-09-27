"""Tests for ``repair_episode_links``.

The command cleans up after the season-blind link scoping described in
:mod:`apps.catalog.management.commands.repair_episode_links`. What matters here
is that it is conservative in both directions: it repairs links that positively
name another episode, and it does not touch anything else — including links
that name nothing at all, which are unknown, not wrong.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import Episode, PlaybackMode, PlaybackSourceGap, Season, Series

PACK = 'https://cdn.example/yA3f/Series/Dexter/S01-S09/'
S06E10 = PACK + 'Dexter.S06E10.1080p.Farsi.Sub.mkv'
S01E10 = PACK + 'Dexter.S01E10.1080p.Farsi.Sub.mkv'


class RepairEpisodeLinksTests(TestCase):
    def series(self, links) -> Series:
        return Series.objects.create(title='Dexter', slug='dexter', download_links=links)

    def episode(self, series, season_number, episode_number, video_url,
                mode=PlaybackMode.GATEWAY) -> Episode:
        season, _ = Season.objects.get_or_create(series=series, season_number=season_number)
        return Episode.objects.create(
            season=season, episode_number=episode_number,
            video_url=video_url, playback_mode=mode, is_published=True,
        )

    def run_command(self, *args) -> str:
        out = StringIO()
        call_command('repair_episode_links', *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    # --- the repair ------------------------------------------------------

    def test_a_wrong_season_link_is_replaced_from_the_pack(self):
        series = self.series([{'url': S06E10}, {'url': S01E10}])
        episode = self.episode(series, 6, 10, S01E10)

        self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, S06E10)

    def test_the_old_verdict_never_survives_the_repair(self):
        """It was earned by a URL the row should never have held."""
        series = self.series([{'url': S06E10}, {'url': S01E10}])
        episode = self.episode(series, 6, 10, S01E10, mode=PlaybackMode.GATEWAY)

        self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.playback_mode, PlaybackMode.UNVERIFIED)
        self.assertIsNone(episode.playback_checked_at)

    def test_no_replacement_is_reported_and_otherwise_left_alone(self):
        """The class that is indistinguishable from a numbering scheme.

        A provider numbering a serial straight through, against a catalogue
        following TMDB seasons, puts every episode in exactly this position.
        Acting on it would reset thousands of verdicts on a guess.
        """
        series = self.series([{'url': S01E10}])
        episode = self.episode(series, 6, 10, S01E10, mode=PlaybackMode.GATEWAY)

        output = self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, S01E10)
        self.assertEqual(episode.playback_mode, PlaybackMode.GATEWAY)
        self.assertFalse(PlaybackSourceGap.objects.filter(object_id=series.pk).exists())
        self.assertIn('orphaned=1', output)

    def test_an_expired_pack_is_a_re_crawl_not_a_mislink(self):
        """The «فندک و شاهزاده خانم» pack: every file expired on the same day.

        A link naming this episode exists; nothing can play it. Swapping one
        unplayable URL for another helps nobody, so the row keeps what it has
        and the title goes into the re-crawl queue.
        """
        base = ('https://cdn.example/Lighter.and.Princess.2022.EP%02d'
                '.480p.SS.mkv?expires=1000000000')
        series = self.series([{'url': base % 2}, {'url': base % 3}])
        episode = self.episode(series, 1, 2, base % 3, mode=PlaybackMode.GATEWAY)

        output = self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, base % 3)
        self.assertEqual(episode.playback_mode, PlaybackMode.GATEWAY)
        self.assertIn('stale=1', output)
        self.assertTrue(PlaybackSourceGap.objects.filter(object_id=series.pk).exists())

    def test_clear_unmatched_leaves_the_stale_class_alone(self):
        """Its links are waiting to be re-signed, not waiting to be deleted."""
        base = ('https://cdn.example/Lighter.and.Princess.2022.EP%02d'
                '.480p.SS.mkv?expires=1000000000')
        series = self.series([{'url': base % 2}, {'url': base % 3}])
        episode = self.episode(series, 1, 2, base % 3)

        self.run_command('--apply', '--clear-unmatched')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, base % 3)

    def test_clear_unmatched_opts_into_that_class(self):
        series = self.series([{'url': S01E10}])
        episode = self.episode(series, 6, 10, S01E10)

        self.run_command('--apply', '--clear-unmatched')

        episode.refresh_from_db()
        self.assertEqual(episode.playback_mode, PlaybackMode.UNVERIFIED)
        self.assertTrue(PlaybackSourceGap.objects.filter(object_id=series.pk).exists())

    def test_clear_unmatched_blanks_the_link(self):
        series = self.series([{'url': S01E10}])
        episode = self.episode(series, 6, 10, S01E10)

        self.run_command('--apply', '--clear-unmatched')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, '')

    # --- what it must leave alone ---------------------------------------

    def test_a_correct_link_is_untouched(self):
        series = self.series([{'url': S06E10}])
        episode = self.episode(series, 6, 10, S06E10, mode=PlaybackMode.DIRECT)

        self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, S06E10)
        self.assertEqual(episode.playback_mode, PlaybackMode.DIRECT)

    def test_a_link_naming_no_episode_is_left_alone(self):
        """Unknown is not wrong; only the sweep gets to judge these."""
        opaque = 'https://cdn.example/6f2a91c4b8.mkv'
        series = self.series([{'url': S06E10}])
        episode = self.episode(series, 6, 10, opaque, mode=PlaybackMode.DIRECT)

        self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, opaque)
        self.assertEqual(episode.playback_mode, PlaybackMode.DIRECT)

    def test_a_padded_episode_number_is_not_a_mislink(self):
        """``E010`` is episode 10. Reading it as somebody else flagged 1,774
        correctly-linked episodes on the first production dry run."""
        padded = PACK + 'Dexter.E010.HardSub.540p.mkv'
        series = self.series([{'url': padded}, {'url': S01E10}])
        episode = self.episode(series, 6, 10, padded, mode=PlaybackMode.DIRECT)

        self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, padded)
        self.assertEqual(episode.playback_mode, PlaybackMode.DIRECT)

    def test_percent_encoded_separators_are_decoded_first(self):
        """``Karen%20Pirie%20S06E10`` puts a digit before the ``S``, which slid
        every word-boundary pattern straight past the pair."""
        encoded = 'https://cdn.example/Karen%20Pirie%20S06E10%20720p%20WEBRip.mkv'
        series = self.series([{'url': encoded}, {'url': S01E10}])
        episode = self.episode(series, 6, 10, encoded, mode=PlaybackMode.DIRECT)

        self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, encoded)
        self.assertEqual(episode.playback_mode, PlaybackMode.DIRECT)

    def test_the_importers_own_numbering_cannot_justify_a_swap(self):
        """Two links naming the same file, one carrying episode metadata that
        disagrees with it. Swapping them repairs nothing and downgrades the
        quality; only the text may decide."""
        hd = PACK + 'Esref.Ruya.S01E26.1080p.mkv'
        sd = PACK + 'Esref.Ruya.S01E26.720p.mkv'
        series = self.series([{'url': hd}, {'url': sd, 'episode_number': 10,
                                           'season_number': 6}])
        episode = self.episode(series, 6, 10, hd, mode=PlaybackMode.GATEWAY)

        self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, hd)
        self.assertEqual(episode.playback_mode, PlaybackMode.GATEWAY)

    def test_a_mislabelled_pack_is_repaired_from_the_file_names(self):
        """The «فندک و شاهزاده خانم» shape, found on the first real dry run.

        The provider's page labels two different files «قسمت ۱», so from the
        third file on every label runs one episode behind the file it names,
        and the importer placed the links by label. Reading the label here
        would make the whole series look unrepairable; the file names say
        plainly what each row should hold.
        """
        base = 'https://cdn.example/Lighter.and.Princess.2022.EP%02d.480p.SS.mkv'
        series = self.series([
            {'url': base % 1, 'label': 'فصل 1 · قسمت 1 · 480p'},
            {'url': base % 2, 'label': 'فصل 1 · قسمت 1 · 480p'},
            {'url': base % 3, 'label': 'فصل 1 · قسمت 2 · 480p'},
        ])
        episode = self.episode(series, 1, 2, base % 3)

        self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, base % 2)

    def test_a_label_cannot_hold_a_row_hostage(self):
        """A correct file name is not made suspect by a label that disagrees."""
        url = 'https://cdn.example/Lighter.and.Princess.2022.EP02.480p.SS.mkv'
        series = self.series([{'url': url, 'label': 'فصل 1 · قسمت 1 · 480p'}])
        episode = self.episode(series, 1, 2, url, mode=PlaybackMode.DIRECT)

        output = self.run_command('--apply')

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, url)
        self.assertEqual(episode.playback_mode, PlaybackMode.DIRECT)
        self.assertIn('mislinked=0', output)

    def test_dry_run_is_the_default_and_writes_nothing(self):
        series = self.series([{'url': S06E10}, {'url': S01E10}])
        episode = self.episode(series, 6, 10, S01E10)

        output = self.run_command()

        episode.refresh_from_db()
        self.assertEqual(episode.video_url, S01E10)
        self.assertEqual(episode.playback_mode, PlaybackMode.GATEWAY)
        self.assertIn('dry run', output)

    def test_it_reports_what_it_found(self):
        series = self.series([{'url': S06E10}, {'url': S01E10}])
        self.episode(series, 6, 10, S01E10)

        output = self.run_command()

        self.assertIn('mislinked=1', output)
