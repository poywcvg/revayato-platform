"""Test the online-playback link of titles that are already on the site.

:mod:`apps.catalog.playback_gate` stops *new* links from being published
untested. This command is the other half: the catalog already holds ~76,000
playback links that were chosen by reading file names, and most of them were
never right. When this was written, 10,495 of 14,207 published movies and
58,666 of 62,050 episodes were serving an MKV as their online source — a
container Safari, iOS and Firefox cannot demux at all.

The sweep is resumable and rate-limited by design. ``playback_checked_at`` is
the cursor: never-checked rows sort first, then the longest ago. Running it
repeatedly walks the whole catalog, and then keeps walking it, because provider
signatures expire in about a day and a link that worked last week is not
evidence about today.

**A failure here is a repair, not a deletion.** A source that is real but
undecodable is marked ``gateway``, so the player asks for an HLS rewrap up
front instead of showing a black frame first. A title with nothing playable
left gets a :class:`PlaybackSourceGap`, which is the queue the throttled
playback crawler already drains by re-crawling providers for a browser-safe
mirror. Only a positive "every candidate answered gone" clears a link, and
only this command may clear one at all — an importer running on a bad network
day must never blank the catalog.

Even that is not allowed on one sighting. Provider CDNs answer the same ranged
GET differently minute to minute (``media_probe`` has the numbers), so a link
is blanked only when a *separate run*, :data:`playback_gate.CLEAR_CONFIRM_HOURS`
or more earlier, already reached the same verdict and the repair queued then did
not find a mirror. The first sighting still records the verdict and still raises
the gap — the hunt for a replacement starts immediately; it is only the
deletion that waits for a second opinion.
"""

from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q
from django.utils import timezone

from apps.catalog import playback_gate
from apps.catalog.models import Episode, Movie, PlaybackMode

#: Rows loaded from the id snapshot at a time. Small enough that a shard's
#: resident set stays flat over a catalogue-sized run, large enough that the
#: per-query overhead disappears next to the network probes each row costs.
FETCH_CHUNK = 200

class Command(BaseCommand):
    help = 'Test published playback links and repair the ones that fail.'

    def add_arguments(self, parser):
        parser.add_argument('--movies', action='store_true', help='Movies only.')
        parser.add_argument('--episodes', action='store_true', help='Episodes only.')
        parser.add_argument('--limit', type=int, default=100, help='Targets per kind.')
        parser.add_argument(
            '--order', choices=['stale', 'popular', 'random'], default='stale',
            help='stale = never checked first, then oldest check (the resume cursor).',
        )
        parser.add_argument(
            '--recheck-hours', type=int, default=168,
            help='Skip rows checked more recently than this. 0 re-tests everything.',
        )
        parser.add_argument(
            '--mode', default='', choices=['', 'direct', 'gateway', 'unverified', 'none'],
            help='Only re-test rows currently carrying this verdict.',
        )
        parser.add_argument(
            '--ids', default='',
            help='Comma-separated ids. Pair with --movies or --episodes.',
        )
        parser.add_argument('--delay', type=float, default=0.0, help='Seconds between targets.')
        parser.add_argument(
            '--shards', type=int, default=1,
            help='Split the catalog into this many disjoint slices by id.',
        )
        parser.add_argument(
            '--shard', type=int, default=0,
            help='Which slice this process takes (0-based). Lets several run at once.',
        )
        parser.add_argument('--no-gaps', action='store_true', help='Do not queue provider re-crawls.')
        parser.add_argument('--dry-run', action='store_true', help='Report without writing.')
        parser.add_argument('--quiet', action='store_true', help='Totals only.')

    def handle(self, *args, **options):
        do_movies = options['movies'] or not options['episodes']
        do_episodes = options['episodes'] or not options['movies']
        if options['ids'] and do_movies and do_episodes:
            raise CommandError('--ids needs --movies or --episodes: ids are per-kind.')
        shards = max(1, int(options['shards'] or 1))
        if not 0 <= int(options['shard'] or 0) < shards:
            raise CommandError(f'--shard must be between 0 and {shards - 1}.')

        started = time.monotonic()
        self.totals = {
            'checked': 0, 'changed': 0, 'cleared': 0, 'held': 0,
            'gaps': 0, 'healed': 0, 'errors': 0,
        }
        self.modes: dict[str, int] = {}
        # One gap row covers a whole series, so a 40-episode season must not
        # bump its report_count forty times in a single pass.
        self.gapped: set[tuple[str, int]] = set()

        if do_movies:
            self._run(Movie, options)
        if do_episodes:
            self._run(Episode, options)

        elapsed = time.monotonic() - started
        breakdown = ' '.join(f'{name}={count}' for name, count in sorted(self.modes.items()))
        totals = self.totals
        self.stdout.write(self.style.SUCCESS(
            f"playback verify: checked={totals['checked']} changed={totals['changed']} "
            f"cleared={totals['cleared']} held={totals['held']} gaps={totals['gaps']} "
            f"healed={totals['healed']} errors={totals['errors']} "
            f"[{breakdown or 'none'}] in {elapsed:.1f}s"
            + (' (dry run)' if options['dry_run'] else '')
        ))

    # -- picking targets ----------------------------------------------------

    def _queryset(self, model, options):
        """The rows worth testing, in the order the resume cursor wants them."""
        if model is Movie:
            qs = Movie.objects.filter(is_published=True)
        else:
            qs = Episode.objects.filter(
                is_published=True,
                season__is_published=True,
                season__series__is_published=True,
            ).select_related('season', 'season__series')

        # A row with no link at all has nothing to test yet — that is the
        # provider crawler's backlog, not this sweep's.
        qs = qs.exclude(video_url='')

        if options['ids']:
            ids = [int(part) for part in options['ids'].split(',') if part.strip().isdigit()]
            return qs.filter(pk__in=ids)

        # Disjoint slices by id so a one-off backfill can run several processes
        # at once without any two of them claiming the same row — the stale
        # cursor alone would hand every process the same head of the queue.
        shards = max(1, int(options['shards'] or 1))
        if shards > 1:
            qs = qs.annotate(_slice=F('pk') % shards).filter(_slice=int(options['shard'] or 0))

        if options['mode']:
            qs = qs.filter(playback_mode=options['mode'])

        hours = int(options['recheck_hours'] or 0)
        if hours > 0:
            cutoff = timezone.now() - timedelta(hours=hours)
            qs = qs.filter(
                Q(playback_checked_at__isnull=True) | Q(playback_checked_at__lt=cutoff)
            )

        order = options['order']
        if order == 'random':
            return qs.order_by('?')
        if order == 'popular':
            return (
                qs.order_by('-view_count', '-popularity', 'pk') if model is Movie
                else qs.order_by('-season__series__view_count', '-view_count', 'pk')
            )
        # 'stale' — never-checked rows lead, then the longest ago. This is what
        # makes the sweep resumable: each run consumes the front of the queue
        # and stamps it, so the next run starts where this one stopped.
        return qs.order_by(F('playback_checked_at').asc(nulls_first=True), 'pk')

    # -- the sweep ----------------------------------------------------------

    def _run(self, model, options):
        limit = max(0, int(options['limit'] or 0))
        if not limit:
            return
        # Take a snapshot of *ids*, then walk it in chunks.
        #
        # It has to be a snapshot: this loop rewrites ``playback_checked_at``,
        # which is the column the queryset is ordered by, so a lazy cursor would
        # re-serve rows it had already stamped and skip others entirely.
        #
        # It has to be ids rather than rows: a full-catalogue shard is twenty
        # thousand episodes, each carrying its subtitle-track JSON and its share
        # of the series link list, and holding them all at once is what got the
        # first attempt at this backfill killed for memory. Ids are eight bytes.
        ids = list(self._queryset(model, options).values_list('pk', flat=True)[:limit])
        delay = max(0.0, float(options['delay'] or 0.0))

        index = 0
        for start in range(0, len(ids), FETCH_CHUNK):
            chunk = ids[start:start + FETCH_CHUNK]
            rows = self._fetch(model, chunk)
            for pk in chunk:
                target = rows.get(pk)
                if target is None:
                    continue  # deleted or unpublished since the snapshot
                if delay and index:
                    time.sleep(delay)
                index += 1
                try:
                    self._verify_one(target, options)
                except Exception as exc:  # one bad row must never end the sweep
                    self.totals['errors'] += 1
                    self.stderr.write(f'  ! {model.__name__} {target.pk}: {exc}')

    def _fetch(self, model, ids) -> dict:
        """Load one chunk of the snapshot, by id and without re-filtering.

        Re-applying the selection filters here would silently drop rows another
        shard, or this run's own earlier chunk, has since re-stamped.
        """
        qs = model.objects.filter(pk__in=ids)
        if model is Episode:
            qs = qs.select_related('season', 'season__series')
        return qs.in_bulk()

    def _verify_one(self, target, options):
        owner, episode = _owner_of(target)
        previous = (target.video_url or '').strip()
        links = playback_gate.candidate_links(owner, episode)

        # Fresh probes, no cache: a sweep exists precisely to catch links that
        # changed since the cached answer, and signed provider URLs expire.
        choice = playback_gate.choose_playback_link(links, current=previous, use_cache=False)

        self.totals['checked'] += 1
        self.modes[choice.mode] = self.modes.get(choice.mode, 0) + 1

        if options['dry_run']:
            if not options['quiet'] and (choice.changed or choice.mode != target.playback_mode):
                self._report(target, choice, prefix=f'{target.playback_mode} -> ')
            return

        # This caller re-probed everything without the cache, so it is the one
        # allowed to act on a "gone" verdict at all — and then only on the
        # second one, hours apart (see the module docstring).
        allow_clear = self._clearing_confirmed(target, choice)
        fields = playback_gate.apply_choice(target, choice, allow_clear=allow_clear)
        if fields:
            target.updated_at = timezone.now()
            target.save(update_fields=[*dict.fromkeys([*fields, 'updated_at'])])
        if choice.changed:
            self.totals['changed'] += 1
        if choice.mode == playback_gate.MODE_NONE and previous:
            self.totals['cleared' if 'video_url' in fields else 'held'] += 1

        # Both failing verdicts want the same repair: go back to the providers
        # for a browser-safe mirror. That queue already exists, and the
        # throttled playback crawler already drains it. Passing a title is the
        # symmetric event and closes the gap, so a title healed by any route —
        # this sweep, the crawler, a manual fix — leaves the queue on its own.
        if not options['no_gaps']:
            if choice.mode in (playback_gate.MODE_GATEWAY, playback_gate.MODE_NONE):
                if self._raise_gap(owner, choice):
                    self.totals['gaps'] += 1
            elif choice.mode == playback_gate.MODE_DIRECT:
                self.totals['healed'] += self._heal_gap(owner)

        if not options['quiet'] and (choice.changed or choice.mode != PlaybackMode.DIRECT):
            self._report(target, choice)

    def _clearing_confirmed(self, target, choice) -> bool:
        """May this verdict actually blank the link, or is it the first sighting?

        Read before :func:`playback_gate.apply_choice` overwrites the stored
        verdict — ``playback_mode`` and ``playback_checked_at`` are what the
        *previous* run concluded, which is exactly the second opinion needed.
        """
        if choice.mode != playback_gate.MODE_NONE:
            return False
        if not choice.tested:
            # ``no_candidates``: every link was skipped before a single request
            # went out — most often because all of this title's signed URLs have
            # expired, which the expired lane refreshes. Nothing was tested, so
            # there is nothing to act on. It is still recorded and still queued
            # for repair; it is simply not evidence that the film is gone.
            return False
        # The row-level half of the rule lives in playback_gate, because the
        # import path reaches the same deletion and has to answer to the same bar.
        return playback_gate.clearing_confirmed(target)

    def _report(self, target, choice, *, prefix: str = ''):
        self.stdout.write(
            f'  {target.__class__.__name__} {target.pk}: {prefix}{choice.mode} '
            f'({choice.reason or "ok"}) tested={choice.tested} dead={len(choice.dead)}'
        )

    def _raise_gap(self, owner, choice) -> bool:
        """Queue a provider re-crawl for a title whose playback link failed."""
        from apps.catalog.playback_sources import upsert_source_gap

        key = (owner.__class__.__name__, owner.pk)
        if key in self.gapped:
            return False
        self.gapped.add(key)

        tech = choice.tech or {}
        diag = {
            'reason': (
                'no_playable_source' if choice.mode == playback_gate.MODE_NONE
                else 'needs_gateway'
            ),
            'containers': [tech['container']] if tech.get('container') else [],
            'codecs': [codec for codec in (tech.get('video'), tech.get('audio')) if codec],
            'unsafe': 1,
        }
        try:
            upsert_source_gap(owner, diag, last_result=f'gate:{choice.reason or choice.mode}')
            return True
        except Exception as exc:
            self.stderr.write(f'  ! gap upsert failed for {owner.pk}: {exc}')
            return False


    def _heal_gap(self, owner) -> int:
        """Close an open gap once the title serves a browser-safe link again."""
        from apps.catalog.playback_sources import resolve_source_gap

        try:
            return int(resolve_source_gap(owner, last_result='gate:direct') or 0)
        except Exception as exc:
            self.stderr.write(f'  ! gap resolve failed for {owner.pk}: {exc}')
            return 0


def _owner_of(target):
    """``(link_owner, episode)`` — an episode's links are stored on its series."""
    if isinstance(target, Episode):
        return target.season.series, target
    return target, None
