"""Repair episodes whose stored playback link belongs to a different episode.

Until the season-aware rewrite of
:func:`catalog.media_verification._link_belongs_to_episode`, an episode's
candidate links were scoped by episode number alone. On a season pack — one
``Series.download_links`` array holding every season's files — «قسمت ۱۰» is
equally true of S01E10 and S06E10, so *every* season's tenth file was offered
as a candidate for the tenth episode of *any* season.

Two things followed. Most episodes drowned: with more candidates than the probe
budget, :func:`playback_gate.choose_playback_link` may never report "gone"
(condemning sources nobody probed is not allowed), so they came back
``unverified`` on every sweep forever. And some episodes were actively
mis-linked: when the episode's own file was dead but another season's tenth
file answered, the sweep adopted that one and stamped it verified. Rick and
Morty S09E08 was left serving S01E08's file, recorded as ``gateway``.

The matcher is fixed, so nothing new is mis-linked. This command cleans up what
the old one already wrote.

What counts as evidence is deliberately narrow, and it is the same evidence on
both sides: the link's own *file name*, via
:func:`media_verification.stated_episode_identity`. Never ``episode_number``,
and never ``label`` — both are written by the same pass over the same provider
page that is under suspicion here, so a check consulting them would agree with
itself. Reading different evidence on the two sides is worse still: it made
every episode of «فندک و شاهزاده خانم», whose provider labels two files
«قسمت ۱», look unrepairable.
A row is repaired only when its link names one episode, that episode is not
this one, and some other link in the same pack names this one. A link that
names nothing, or names two things at once, is left alone: neither silence nor
ambiguity is a mistake.

When no replacement can be installed, the reason decides what happens, and
there are two very different reasons.

*Stale* — the pack does name this episode, with a link nothing can play: the
host is gone, or the signed URL has expired. «فندک و شاهزاده خانم» is 36 files
that all expired on the same day. Swapping one unplayable URL for another helps
nobody, so the row is left as it stands and a ``PlaybackSourceGap`` is raised,
which is what puts the title in the re-crawl queue. Run this command again
after the refresh lane has re-signed the pack and the repair becomes possible.

*Orphaned* — nothing in the pack names this episode at all. It reads as a
mislink, but it reads just as well as a numbering scheme we do not speak: a
serial the provider numbers straight through while the catalogue follows TMDB
seasons produces exactly this shape on every one of its episodes (Esref Ruya's
``S01E14`` is the catalogue's S02E01). Suspicion is not proof, so this is
reported and nothing else. ``--clear-unmatched`` acts on that class anyway,
blanking the link and opening a gap for the crawler.

The repair itself never invents a verdict. The replacement is installed and the
row reset to ``unverified`` with a null check cursor, which puts it at the head
of the sweep's queue to be tested for real.

Dry run by default. Nothing is written without ``--apply``.

    python manage.py repair_episode_links                 # report only
    python manage.py repair_episode_links --apply
    python manage.py repair_episode_links --apply --clear-unmatched
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import F

from apps.catalog import playback_gate
from apps.catalog.media_verification import (
    _link_url, episode_identity_matches, stated_episode_identity,
)
from apps.catalog.models import Episode, PlaybackMode, Series
from apps.catalog.playback_refresh import link_playable

#: Episode rows loaded per query. Deliberately small, and deliberately not
#: joined to Series: a series' ``download_links`` is megabytes on the biggest
#: packs, and a scan that dragged one along for each of ~50k episodes filled a
#: 768 MiB container in two minutes. The pack is only needed for a row that
#: turns out to be mislinked, so it is fetched there — a hundred-odd times in a
#: full run instead of fifty thousand.
FETCH_CHUNK = 500


class Command(BaseCommand):
    help = 'Repair episodes whose playback link names a different episode.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write the repairs (default: report only).')
        parser.add_argument('--clear-unmatched', action='store_true',
                            help='Also act on the orphaned class — links nothing in '
                                 'the pack names: blank them and queue a re-crawl. '
                                 'Off by default; see the note in _repair_one. Does '
                                 'not touch the stale class, whose links are only '
                                 'waiting to be re-signed.')
        parser.add_argument('--limit', type=int, default=0,
                            help='Stop after this many episodes are examined.')
        parser.add_argument('--ids', default='',
                            help='Comma-separated episode ids, instead of a full scan.')
        parser.add_argument('--quiet', action='store_true',
                            help='Totals only, no per-row lines.')

    def handle(self, *args, **options):
        self.apply = bool(options['apply'])
        self.quiet = bool(options['quiet'])
        self.clear_unmatched = bool(options['clear_unmatched'])
        totals = {'examined': 0, 'mislinked': 0, 'replaced': 0,
                  'stale': 0, 'orphaned': 0, 'cleared': 0, 'gaps': 0, 'errors': 0}

        for episode in self._rows(options):
            totals['examined'] += 1
            try:
                self._repair_one(episode, totals)
            except Exception as exc:  # one bad row must never end the run
                totals['errors'] += 1
                self.stderr.write(f'  ! Episode {episode.pk}: {exc}')

        verb = 'repaired' if self.apply else 'would repair'
        self.stdout.write(self.style.SUCCESS(
            f'examined={totals["examined"]} mislinked={totals["mislinked"]} '
            f'({verb}: replaced={totals["replaced"]} cleared={totals["cleared"]}) '
            f'stale={totals["stale"]} orphaned={totals["orphaned"]} '
            f'gaps={totals["gaps"]} errors={totals["errors"]}'
        ))
        if not self.apply and totals['mislinked']:
            self.stdout.write('dry run — re-run with --apply to write these.')

    def _rows(self, options):
        """Episodes with a stored link, most-recently-checked first.

        Recency first because the damage is recent: the rows a sweep stamped
        in the last hours are the ones a viewer is most likely to open next,
        so a ``--limit`` run repairs those before it works backwards.
        """
        qs = Episode.objects.filter(is_published=True).exclude(video_url='')
        if options['ids']:
            ids = [int(part) for part in options['ids'].split(',') if part.strip()]
            qs = qs.filter(pk__in=ids)
        ids = list(
            qs.order_by(F('playback_checked_at').desc(nulls_last=True), 'pk')
            .values_list('pk', flat=True)[:options['limit'] or None]
        )
        for start in range(0, len(ids), FETCH_CHUNK):
            chunk = (
                Episode.objects.filter(pk__in=ids[start:start + FETCH_CHUNK])
                .select_related('season')
                .only('video_url', 'episode_number', 'playback_mode',
                      'playback_checked_at', 'season__season_number',
                      'season__series_id')
            )
            yield from chunk

    def _repair_one(self, episode, totals):
        url = (episode.video_url or '').strip()
        # Narrow on purpose: a link that names nothing — or names two things —
        # is not evidence of a mistake, only a link that names somebody else.
        stated = stated_episode_identity(url)
        if stated is None or episode_identity_matches(stated, episode):
            return

        totals['mislinked'] += 1
        # Only now is the pack worth reading; see FETCH_CHUNK.
        series = Series.objects.get(pk=episode.season.series_id)
        replacement, pack_names_it = self._replacement(series, episode, url)
        label = (f'ep {episode.pk} S{episode.season.season_number:02d}'
                 f'E{episode.episode_number:03d}')

        fields: list[str] = []
        if replacement:
            episode.video_url = replacement
            fields.append('video_url')
            totals['replaced'] += 1
            action = f'-> {replacement.rsplit("/", 1)[-1][:64]}'
        elif pack_names_it:
            # The pack does name this episode — with a link nothing can play
            # right now, because the host is gone or the signature expired.
            # Swapping one unplayable URL for another helps nobody; what this
            # title needs is fresh links, so raise the gap that puts it in the
            # re-crawl queue and leave the row as it stands.
            totals['stale'] += 1
            if not self.quiet:
                self.stdout.write(
                    f'  {label} was {url.rsplit("/", 1)[-1][:64]} '
                    f'-> queued a re-crawl (its own link is expired)')
            if self.apply and self._raise_gap(series, 'repair:expired-pack'):
                totals['gaps'] += 1
            return
        elif not self.clear_unmatched:
            # Nothing in the pack names this episode at all. That reads as a
            # mislink, but it reads just as well as a numbering scheme we do
            # not speak — a serial the provider numbers straight through while
            # the catalogue follows TMDB seasons looks exactly like this, on
            # every one of its episodes. Suspicion is not proof, and resetting
            # a verdict costs a viewer a link that may be perfectly good, so
            # by default this is reported and nothing else.
            totals['orphaned'] += 1
            if not self.quiet:
                self.stdout.write(
                    f'  {label} was {url.rsplit("/", 1)[-1][:64]} '
                    f'-> left alone (nothing in the pack names this episode)')
            return
        else:
            episode.video_url = ''
            fields.append('video_url')
            totals['cleared'] += 1
            action = '-> cleared (nothing in the pack names this episode)'

        # Never carry the old verdict over: it was earned by a URL this row
        # either no longer holds or should never have held. Unverified with a
        # null cursor is the front of the sweep's queue, not a claim.
        if episode.playback_mode != PlaybackMode.UNVERIFIED:
            episode.playback_mode = PlaybackMode.UNVERIFIED
            fields.append('playback_mode')
        episode.playback_checked_at = None
        fields.append('playback_checked_at')

        if not self.quiet:
            self.stdout.write(f'  {label} was {url.rsplit("/", 1)[-1][:64]} {action}')

        if not self.apply:
            return

        # ``updated_at`` is auto_now, but only when update_fields names it.
        episode.save(update_fields=[*dict.fromkeys([*fields, 'updated_at'])])
        if not replacement and self._raise_gap(series):
            totals['gaps'] += 1

    def _replacement(self, series, episode, wrong_url: str) -> tuple[str, bool]:
        """``(best link whose file name names this episode, did any name it)``.

        The two answers differ, and the difference decides what happens next.
        A pack can name this episode and still offer nothing usable — «فندک و
        شاهزاده خانم» is 36 files that all expired on the 17th. That is a
        re-crawl, not a mislink, and it must not be reported as one.

        Ranked by the gate's own heuristic, so the link installed here is the
        one the gate would test first anyway.
        """
        scoped = []
        for item in (getattr(series, 'download_links', None) or []):
            if not isinstance(item, dict):
                continue
            url = _link_url(item)
            if not url or url == wrong_url:
                continue
            # Its own file name has to name this episode — the same witness
            # the row was judged by, or the two sides are reading different
            # evidence and the comparison means nothing. Accepting ``label`` or
            # the stored ``episode_number`` here would let the command swap one
            # link for another naming the very same episode on disk, which is a
            # metadata disagreement rather than a mislink.
            if episode_identity_matches(stated_episode_identity(url), episode):
                scoped.append(item)
        for item in playback_gate.rank_candidates(scoped):
            url = str(item.get('url') or '').strip()
            # The gate ranks lapsed links on purpose: it answers "would this
            # play once re-signed", which is what keeps a title on the air while
            # its tokens refresh. This command needs the other question. A link
            # no viewer can be handed right now is not a repair, so the expiry
            # and dead-host check has to happen here rather than be inherited
            # from the ranking — otherwise the stale pack reads as a mislink and
            # one unplayable URL is swapped for another.
            if url and link_playable(item):
                return url, True
        return '', bool(scoped)

    def _raise_gap(self, series, reason: str = 'repair:mislinked') -> bool:
        """Queue a provider re-crawl: this episode has no usable link to hold."""
        from apps.catalog.playback_sources import upsert_source_gap

        diag = {'reason': 'no_playable_source', 'containers': [], 'codecs': [], 'unsafe': 1}
        try:
            upsert_source_gap(series, diag, last_result=reason)
            return True
        except Exception as exc:
            self.stderr.write(f'  ! gap upsert failed for series {series.pk}: {exc}')
            return False
