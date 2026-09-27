"""Fill Season/Episode metadata from TMDB.

Episode rows are materialised from provider download links
(``ensure_episodes_from_download_links``), which only knows the season/episode
numbers a link filename exposes. Every row therefore starts with a stub
«قسمت N» title and no description, air date, runtime or still image. This
module walks those rows season by season and completes them from
``TMDBClient.tv_season_details``, which merges the English payload in wherever
the Persian localisation is blank.

One TMDB request covers a whole season, so a series with 4 seasons costs 4
requests regardless of how many episodes it has.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from .ingestion import _download_tmdb_image, _tmdb_image_url
from .models import Episode, Season, Series
from .tmdb import TMDBError, configured_tmdb_client

logger = logging.getLogger(__name__)

# Titles the link-derived materializer generates. They carry no information
# beyond the episode number that is already stored in its own column, so TMDB
# names may overwrite them.
_STUB_EPISODE_TITLE = re.compile(r'^\s*(?:قسمت|اپیزود|episode|ep\.?|e)\s*0*(\d+)\s*$', re.I)
_STUB_SEASON_TITLE = re.compile(r'^\s*(?:فصل|season|s)\s*0*(\d+)\s*$', re.I)

# Bidi formatting characters the materializer embeds in stub titles.
_BIDI_MARKS = {ord(char): None for char in '‎‏‪‫‬‭‮⁦⁧⁨⁩﻿'}

# Stamp written to ``Series.source_metadata`` so a recurring pass can skip
# series it has already completed instead of re-spending TMDB calls on them.
STAMP_KEY = 'episode_metadata'


def _is_stub_title(value: str, pattern: re.Pattern[str]) -> bool:
    # The link-derived titles are stored with bidi control marks (U+202B …) so
    # they render correctly in LTR contexts; strip them before matching or every
    # stub looks like a real title.
    text = str(value or '').translate(_BIDI_MARKS).strip()
    return not text or bool(pattern.match(text))


def _recheck_cutoff():
    days = max(0, int(getattr(settings, 'EPISODE_METADATA_RECHECK_DAYS', 14)))
    return timezone.now() - timedelta(days=days) if days else None


def _stamp_series(series, payload: dict) -> None:
    """Record the last completion attempt without clobbering sibling metadata."""
    meta = dict(series.source_metadata or {})
    meta[STAMP_KEY] = {
        'at': timezone.now().isoformat(),
        'seasons': int(payload.get('seasons_updated', 0)),
        'episodes': int(payload.get('episodes_updated', 0)),
        'missing': int(payload.get('episodes_missing', 0)),
    }
    series.source_metadata = meta
    series.save(update_fields=['source_metadata', 'updated_at'])


def _season_fields_from_tmdb(season, details: dict) -> list[str]:
    """Apply season-level TMDB metadata; return the changed field names."""
    fields: list[str] = []
    tmdb_id = details.get('id') or None
    if tmdb_id and season.tmdb_id != int(tmdb_id):
        # ``Season.tmdb_id`` is globally unique; another row may already own it
        # (TMDB occasionally reuses ids across merged series entries).
        if not Season.objects.filter(tmdb_id=int(tmdb_id)).exclude(pk=season.pk).exists():
            season.tmdb_id = int(tmdb_id)
            fields.append('tmdb_id')

    title = str(details.get('name') or '').strip()[:255]
    if (
        title
        and _is_stub_title(season.title, _STUB_SEASON_TITLE)
        and not _is_stub_title(title, _STUB_SEASON_TITLE)
    ):
        season.title = title
        fields.append('title')

    description = str(details.get('overview') or '').strip()
    if description and not (season.description or '').strip():
        season.description = description
        fields.append('description')

    air_date = parse_date(str(details.get('air_date') or ''))
    if air_date:
        if season.air_date != air_date:
            season.air_date = air_date
            fields.append('air_date')
        if season.release_year != air_date.year:
            season.release_year = air_date.year
            fields.append('release_year')

    poster = _tmdb_image_url(details.get('poster_path'), 'w500')
    if poster and not (season.poster_external_url or '').strip():
        season.poster_external_url = poster
        fields.append('poster_external_url')
    return fields


def _episode_fields_from_tmdb(episode, payload: dict, *, stills: bool, alt_title: str = '') -> list[str]:
    """Apply episode-level TMDB metadata; return the changed field names."""
    fields: list[str] = []
    title = str(payload.get('name') or '').strip()[:255]
    # TMDB's Persian localisation is frequently just «قسمت N». When it is, the
    # English name is a real improvement over another numbered stub.
    if _is_stub_title(title, _STUB_EPISODE_TITLE) and alt_title:
        title = str(alt_title).strip()[:255]
    # Overwriting «قسمت 3» with an equally generic "Episode 3" would only trade a
    # Persian stub for an English one.
    if (
        title
        and _is_stub_title(episode.title, _STUB_EPISODE_TITLE)
        and not _is_stub_title(title, _STUB_EPISODE_TITLE)
    ):
        episode.title = title
        fields.append('title')

    description = str(payload.get('overview') or '').strip()
    if description and not (episode.description or '').strip():
        episode.description = description
        fields.append('description')

    air_date = parse_date(str(payload.get('air_date') or ''))
    if air_date and episode.air_date != air_date:
        episode.air_date = air_date
        fields.append('air_date')

    try:
        runtime = int(payload.get('runtime') or 0)
    except (TypeError, ValueError):
        runtime = 0
    if runtime > 0 and not episode.duration_minutes:
        episode.duration_minutes = runtime
        fields.append('duration_minutes')

    # Stills are the only part that costs a per-episode HTTP download, so they
    # stay opt-in for the recurring pass.
    if stills and payload.get('still_path') and not getattr(episode.poster, 'name', ''):
        content = _download_tmdb_image(
            payload['still_path'], size='w300',
            basename=f'episode-{episode.pk}',
        )
        if content is not None:
            episode.poster.save(content.name, content, save=False)
            fields.append('poster')
    return fields


def _fallback_episode_names(client, series_tmdb_id: int, season_number: int) -> dict[int, str]:
    """English episode names, used only where the Persian ones are numbered stubs."""
    language = getattr(client, 'fallback_language', '') or ''
    if not language or language == getattr(client, 'language', ''):
        return {}
    try:
        details = client.tv_season_details(series_tmdb_id, season_number, language=language)
    except TMDBError:
        return {}
    names: dict[int, str] = {}
    for item in details.get('episodes') or []:
        if not isinstance(item, dict) or item.get('episode_number') is None:
            continue
        name = str(item.get('name') or '').strip()
        if name and not _is_stub_title(name, _STUB_EPISODE_TITLE):
            names[int(item['episode_number'])] = name
    return names


def complete_series_episode_metadata(
    series,
    *,
    client=None,
    stills: bool = False,
    delay: float = 0.0,
    should_cancel=None,
) -> dict:
    """Complete Season/Episode metadata for one series from TMDB."""
    result = {
        'series_id': series.pk,
        'tmdb_id': series.tmdb_id,
        'seasons_seen': 0,
        'seasons_updated': 0,
        'episodes_seen': 0,
        'episodes_updated': 0,
        'episodes_missing': 0,
        'errors': 0,
        'status': 'ok',
    }
    if not series.tmdb_id:
        result['status'] = 'no_tmdb_id'
        return result

    client = client or configured_tmdb_client()
    seasons = list(Season.objects.filter(series=series).order_by('season_number'))
    if not seasons:
        result['status'] = 'no_seasons'
        return result

    for season in seasons:
        if callable(should_cancel) and should_cancel():
            result['status'] = 'cancelled'
            break
        result['seasons_seen'] += 1
        try:
            details = client.tv_season_details(series.tmdb_id, season.season_number)
        except TMDBError as exc:
            # A missing season on TMDB (provider numbering drift) must not abort
            # the remaining seasons of the same series.
            logger.info(
                'episode_metadata season lookup failed series=%s season=%s: %s',
                series.pk, season.season_number, exc,
            )
            result['errors'] += 1
            continue
        if delay:
            time.sleep(delay)

        episodes = {
            int(item['episode_number']): item
            for item in (details.get('episodes') or [])
            if isinstance(item, dict) and item.get('episode_number') is not None
        }
        rows = list(Episode.objects.filter(season=season).order_by('episode_number'))
        # Only pay for the English season payload when a stub title could
        # actually be improved by it.
        alt_names: dict[int, str] = {}
        if any(
            _is_stub_title(str(episodes.get(int(row.episode_number or 0), {}).get('name') or ''),
                           _STUB_EPISODE_TITLE)
            and _is_stub_title(row.title, _STUB_EPISODE_TITLE)
            for row in rows
        ):
            alt_names = _fallback_episode_names(client, series.tmdb_id, season.season_number)
            if delay:
                time.sleep(delay)
        with transaction.atomic():
            season_fields = _season_fields_from_tmdb(season, details)
            # ``episode_count`` describes what the site actually carries, not
            # what TMDB lists, so it tracks the real rows.
            if rows and season.episode_count != len(rows):
                season.episode_count = len(rows)
                season_fields.append('episode_count')
            if season_fields:
                try:
                    season.save(update_fields=[*dict.fromkeys(season_fields), 'updated_at'])
                    result['seasons_updated'] += 1
                except IntegrityError:
                    # Lost a race on the unique ``tmdb_id``; retry without it.
                    retry = [name for name in season_fields if name != 'tmdb_id']
                    season.tmdb_id = None
                    if retry:
                        season.save(update_fields=[*dict.fromkeys(retry), 'updated_at'])
                        result['seasons_updated'] += 1

            for episode in rows:
                result['episodes_seen'] += 1
                payload = episodes.get(int(episode.episode_number or 0))
                if not payload:
                    result['episodes_missing'] += 1
                    continue
                fields = _episode_fields_from_tmdb(
                    episode, payload, stills=stills,
                    alt_title=alt_names.get(int(episode.episode_number or 0), ''),
                )
                if fields:
                    episode.save(update_fields=[*dict.fromkeys(fields), 'updated_at'])
                    result['episodes_updated'] += 1
    return result


def series_needing_episode_metadata(*, force: bool = False):
    """Published series with TMDB ids whose episodes still look incomplete."""
    incomplete = Episode.objects.filter(season__series_id=OuterRef('pk')).filter(
        Q(description='') | Q(air_date__isnull=True) | Q(duration_minutes__isnull=True)
        # Stub titles carry bidi marks, so the pattern tolerates a leading run of
        # non-alphanumeric formatting characters.
        | Q(title='') | Q(title__regex=r'^[^0-9A-Za-zآ-ی]*(قسمت|اپیزود|Episode|EP)[^0-9]*[0-9]+$'),
    )
    qs = (
        Series.objects.filter(is_published=True, tmdb_id__isnull=False)
        .filter(Exists(incomplete))
    )
    cutoff = _recheck_cutoff()
    if not force and cutoff is not None:
        # Skip series completed recently: anything still blank after a pass is
        # usually missing upstream, and re-asking TMDB every hour is pure cost.
        # This must be a pk subquery — ``exclude()`` on a JSON key transform also
        # drops every row where the key is absent (NULL), i.e. all of them.
        recent = Series.objects.filter(
            source_metadata__episode_metadata__at__gte=cutoff.isoformat(),
        ).values('pk')
        qs = qs.exclude(pk__in=recent)
    return qs.order_by('-updated_at')


def complete_missing_episode_metadata(
    *,
    series_limit: int | None = None,
    stills: bool | None = None,
    delay: float | None = None,
    force: bool = False,
    should_cancel=None,
    on_progress=None,
) -> dict:
    """Walk series with incomplete episodes and fill them from TMDB."""
    if stills is None:
        stills = bool(getattr(settings, 'EPISODE_METADATA_STILLS', False))
    if delay is None:
        delay = float(getattr(settings, 'EPISODE_METADATA_DELAY_SECONDS', 0.15))
    if series_limit is None:
        series_limit = int(getattr(settings, 'EPISODE_METADATA_SERIES_PER_TICK', 25))

    stats = {
        'series_considered': 0,
        'series_updated': 0,
        'series_skipped': 0,
        'seasons_updated': 0,
        'episodes_updated': 0,
        'episodes_missing': 0,
        'errors': 0,
        'cancelled': False,
    }
    queryset = series_needing_episode_metadata(force=force)
    if series_limit and series_limit > 0:
        queryset = queryset[:series_limit]
    candidates = list(queryset)
    if not candidates:
        return stats

    client = configured_tmdb_client()
    for series in candidates:
        if callable(should_cancel) and should_cancel():
            stats['cancelled'] = True
            break
        stats['series_considered'] += 1
        try:
            row = complete_series_episode_metadata(
                series, client=client, stills=stills, delay=delay,
                should_cancel=should_cancel,
            )
        except Exception as exc:  # pragma: no cover — one bad series must not stop the pass
            logger.warning('episode_metadata failed series=%s: %s', series.pk, exc)
            stats['errors'] += 1
            continue
        stats['seasons_updated'] += row['seasons_updated']
        stats['episodes_updated'] += row['episodes_updated']
        stats['episodes_missing'] += row['episodes_missing']
        stats['errors'] += row['errors']
        if row['episodes_updated'] or row['seasons_updated']:
            stats['series_updated'] += 1
        else:
            stats['series_skipped'] += 1
        if row['status'] == 'cancelled':
            stats['cancelled'] = True
            break
        # Stamp even when nothing changed, otherwise a series TMDB has no data
        # for is re-selected on every single tick forever.
        _stamp_series(series, row)
        if callable(on_progress):
            on_progress(stats, series)
    return stats
