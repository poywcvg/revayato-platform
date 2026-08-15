#!/usr/bin/env python3
"""Fixup Legend (2015) + Eşref Rüya (اشرف رویا): full metadata + accurate seasons.

- Legend: refresh TMDB metadata, set Persian title «لجند».
- Eşref Rüya: refresh TMDB metadata, set Persian title «اشرف رویا», remap the
  provider's absolute episode numbering (1..47 in S1) to the canonical TMDB
  structure (S1 = E1..13, S2 = E1..34 mapped from absolute 14..47), sync
  download-link season/episode stamps + labels, then queue SoftSub WebVTT.

Run inside the backend container (rootfs is read-only; pipe via stdin):

  docker exec -i revayato-backend-1 python - < backend/scripts/fixup_legend_esref.py
  ... --dry-run / --skip-softsub
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

for _candidate in (Path('/app'), Path.cwd()):
    if (_candidate / 'config' / 'settings.py').exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

LEGEND_TMDB_ID = 276907
LEGEND_PERSIAN_TITLE = 'لجند'
LEGEND_ORIGINAL_TITLE = 'Legend'
LEGEND_SLUG = 'لجند'

ESREF_TMDB_ID = 283123
ESREF_PERSIAN_TITLE = 'اشرف رویا'
ESREF_ORIGINAL_TITLE = 'Eşref Rüya'
ESREF_S1_EPISODES = 13  # TMDB: S1 = 13 eps, S2 = 34 eps (47 total)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--skip-softsub', action='store_true')
    args = parser.parse_args()

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.cache import bump_catalog_cache_version
    from apps.catalog.importer_config import get_importer_settings
    from apps.catalog.ingestion import attach_tmdb_artwork, upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.models import Episode, Movie, Season, Series
    from apps.catalog.subtitle_extract import ensure_episodes_from_download_links
    from apps.catalog.tasks import enqueue_series_softsub
    from apps.catalog.tmdb import configured_tmdb_client
    from apps.catalog.top_catalog import _publish_movie, _publish_series

    client = configured_tmdb_client()
    importer = get_importer_settings()

    # ------------------------------------------------------------------ movie
    print('=== MOVIE Legend (2015) ===', flush=True)
    movie = Movie.objects.filter(tmdb_id=LEGEND_TMDB_ID).first()
    if movie is None:
        print('ERROR: movie missing — run import_legend_esref.py first', file=sys.stderr)
        return 1
    details = client.movie_details(LEGEND_TMDB_ID)
    movie, created, _, _ = upsert_tmdb_movie(
        details,
        importer=importer,
        dry_run=args.dry_run,
    )
    fields: list[str] = []
    if (movie.title or '').strip() != LEGEND_PERSIAN_TITLE:
        movie.title = LEGEND_PERSIAN_TITLE
        fields.append('title')
    if (movie.original_title or '').strip() != LEGEND_ORIGINAL_TITLE:
        movie.original_title = LEGEND_ORIGINAL_TITLE
        fields.append('original_title')
    if movie.slug != LEGEND_SLUG:
        movie.slug = LEGEND_SLUG
        fields.append('slug')
    if not movie.is_featured:
        movie.is_featured = True
        fields.append('is_featured')
    if not movie.is_recommended:
        movie.is_recommended = True
        fields.append('is_recommended')
    if fields and not args.dry_run:
        movie.save(update_fields=[*fields, 'updated_at'])
    _publish_movie(movie) if not args.dry_run else None
    print(
        f'  pk={movie.pk} title={movie.title!r} year={movie.release_year} '
        f'dur={movie.duration_minutes} imdb={movie.imdb_rating} fields={fields} '
        f'links={len(movie.download_links or [])} tracks={len(movie.subtitle_tracks or [])} '
        f'pub={movie.is_published}',
        flush=True,
    )

    # ----------------------------------------------------------------- series
    print('\n=== SERIES Eşref Rüya / اشرف رویا ===', flush=True)
    series = Series.objects.filter(tmdb_id=ESREF_TMDB_ID).first()
    if series is None:
        print('ERROR: series missing — run import_legend_esref.py first', file=sys.stderr)
        return 1
    details = client.tv_details(ESREF_TMDB_ID)
    series, _ = upsert_tmdb_series(
        details,
        importer=importer,
        dry_run=args.dry_run,
    )
    fields = []
    if (series.title or '').strip() != ESREF_PERSIAN_TITLE:
        series.title = ESREF_PERSIAN_TITLE
        fields.append('title')
    if (series.original_title or '').strip() != ESREF_ORIGINAL_TITLE:
        series.original_title = ESREF_ORIGINAL_TITLE
        fields.append('original_title')
    if not series.is_featured:
        series.is_featured = True
        fields.append('is_featured')
    if fields and not args.dry_run:
        series.save(update_fields=[*fields, 'updated_at'])
    if not args.dry_run:
        _publish_series(series)
    print(
        f'  pk={series.pk} title={series.title!r} year={series.start_year} '
        f'seasons_tmdb={(series.source_metadata or {}).get("number_of_seasons")} '
        f'eps_tmdb={(series.source_metadata or {}).get("number_of_episodes")} '
        f'fields={fields}',
        flush=True,
    )

    # ---- remap absolute provider numbering → TMDB S1 (1-13) + S2 (1-34)
    links = [dict(item) for item in (series.download_links or []) if isinstance(item, dict)]
    moved_links = 0
    for item in links:
        season_no = item.get('season_number')
        episode_no = item.get('episode_number')
        if season_no == 1 and isinstance(episode_no, int) and episode_no > ESREF_S1_EPISODES:
            new_ep = episode_no - ESREF_S1_EPISODES
            item['season_number'] = 2
            item['episode_number'] = new_ep
            label = str(item.get('label') or '')
            quality = label.split('·', 1)[1].strip() if '·' in label else str(item.get('quality') or '').strip()
            item['label'] = f'فصل 2 · قسمت {new_ep}' + (f' · {quality}' if quality else '')
            moved_links += 1
    print(f'  links total={len(links)} moved_to_s2={moved_links}', flush=True)

    if args.dry_run:
        eps = Episode.objects.filter(season__series=series)
        print(
            f'  DRY seasons={Season.objects.filter(series=series).count()} eps={eps.count()} '
            f'expected=S1:{ESREF_S1_EPISODES},S2:{max(0, len({item.get("episode_number") for item in links if item.get("season_number") == 2 and isinstance(item.get("episode_number"), int)}))}',
            flush=True,
        )
        return 0

    series.download_links = links
    series.save(update_fields=['download_links', 'updated_at'])

    season2, s2_created = Season.objects.get_or_create(
        series=series,
        season_number=2,
        defaults={'title': 'فصل 2', 'is_published': True, 'episode_count': 0},
    )
    if not season2.is_published:
        season2.is_published = True
        season2.save(update_fields=['is_published', 'updated_at'])
    print(f'  season2 pk={season2.pk} created={s2_created}', flush=True)

    season1 = Season.objects.get(series=series, season_number=1)
    moved_eps = 0
    for ep in Episode.objects.filter(season=season1, episode_number__gt=ESREF_S1_EPISODES):
        new_no = ep.episode_number - ESREF_S1_EPISODES
        target = Episode.objects.filter(season=season2, episode_number=new_no).first()
        if target is not None:
            merge_fields = []
            for field_name in (
                'description', 'duration_minutes', 'poster', 'video_url',
                'trailer_url', 'download_key', 'subtitle_tracks', 'air_date',
            ):
                if getattr(target, field_name) in (None, '', []) and getattr(ep, field_name) not in (None, '', []):
                    setattr(target, field_name, getattr(ep, field_name))
                    merge_fields.append(field_name)
            if not target.is_published:
                target.is_published = True
                merge_fields.append('is_published')
            if merge_fields:
                target.save(update_fields=[*merge_fields, 'updated_at'])
            ep.delete()
            moved_eps += 1
            continue
        ep.season = season2
        ep.episode_number = new_no
        ep.title = f'قسمت {new_no}'
        ep.is_published = True
        ep.save(update_fields=['season', 'episode_number', 'title', 'is_published', 'updated_at'])
        moved_eps += 1
    print(f'  episodes moved to S2={moved_eps}', flush=True)

    # Re-sync episode video URLs from the remapped link scoping (no-op for rows
    # that already carry the preferred playable URL).
    synced = ensure_episodes_from_download_links(series) or 0
    print(f'  ensure_episodes created={synced}', flush=True)

    for season in (season1, season2):
        count = Episode.objects.filter(season=season, is_published=True).count()
        if season.episode_count != count:
            season.episode_count = count
            season.save(update_fields=['episode_count', 'updated_at'])

    s1_eps = Episode.objects.filter(season=season1).count()
    s2_eps = Episode.objects.filter(season=season2).count()
    s2_video = Episode.objects.filter(season=season2).exclude(video_url='').exclude(video_url__isnull=True).count()
    print(f'  final: S1 eps={s1_eps} | S2 eps={s2_eps} video={s2_video}', flush=True)

    # TMDB season endpoints carry the episode-level metadata omitted from the
    # series details payload.  Fill it without touching provider playback URLs
    # or already extracted subtitle tracks.
    from django.utils.dateparse import parse_date

    metadata_updates = 0
    episode_artwork = 0
    for season_number in (1, 2):
        localized = client._request(f'tv/{ESREF_TMDB_ID}/season/{season_number}')
        english = client._request(
            f'tv/{ESREF_TMDB_ID}/season/{season_number}',
            language='en-US',
        )
        turkish = client._request(
            f'tv/{ESREF_TMDB_ID}/season/{season_number}',
            language='tr-TR',
        )
        season = Season.objects.get(series=series, season_number=season_number)
        season_fields = []
        season_tmdb_id = localized.get('id') or english.get('id')
        if season_tmdb_id and season.tmdb_id != int(season_tmdb_id):
            season.tmdb_id = int(season_tmdb_id)
            season_fields.append('tmdb_id')
        season_name = (
            localized.get('name') or turkish.get('name') or english.get('name') or ''
        ).strip()
        if season_name and season.title != season_name:
            season.title = season_name
            season_fields.append('title')
        season_description = (
            localized.get('overview') or turkish.get('overview') or english.get('overview') or ''
        ).strip()
        if season_description and season.description != season_description:
            season.description = season_description
            season_fields.append('description')
        season_air_date = parse_date(
            localized.get('air_date') or turkish.get('air_date') or english.get('air_date') or ''
        )
        if season_air_date and season.air_date != season_air_date:
            season.air_date = season_air_date
            season.release_year = season_air_date.year
            season_fields.extend(['air_date', 'release_year'])
        poster_path = (
            localized.get('poster_path') or turkish.get('poster_path') or english.get('poster_path')
        )
        if poster_path and not season.poster:
            art_fields = attach_tmdb_artwork(
                season,
                {'id': season_tmdb_id, 'poster_path': poster_path},
                prefix=f'esref-season-{season_number}',
                allow_poster_backdrop=False,
            )
            season_fields.extend(art_fields)
        if season_fields:
            season.save(update_fields=[*dict.fromkeys(season_fields), 'updated_at'])
            metadata_updates += 1

        localized_eps = {
            int(item.get('episode_number')): item
            for item in localized.get('episodes') or []
            if item.get('episode_number') is not None
        }
        english_eps = {
            int(item.get('episode_number')): item
            for item in english.get('episodes') or []
            if item.get('episode_number') is not None
        }
        turkish_eps = {
            int(item.get('episode_number')): item
            for item in turkish.get('episodes') or []
            if item.get('episode_number') is not None
        }
        for episode in Episode.objects.filter(season=season).order_by('episode_number'):
            local_item = localized_eps.get(episode.episode_number, {})
            english_item = english_eps.get(episode.episode_number, {})
            turkish_item = turkish_eps.get(episode.episode_number, {})
            if not local_item and not english_item and not turkish_item:
                continue
            episode_fields = []
            episode_name = (
                local_item.get('name') or turkish_item.get('name') or english_item.get('name') or ''
            ).strip()
            if episode_name and episode.title != episode_name:
                episode.title = episode_name
                episode_fields.append('title')
            episode_description = (
                local_item.get('overview') or turkish_item.get('overview')
                or english_item.get('overview') or ''
            ).strip()
            if not episode_description:
                episode_description = (
                    f'قسمت {episode.episode_number} از فصل {season_number} سریال اشرف رویا.'
                )
            if episode_description and episode.description != episode_description:
                episode.description = episode_description
                episode_fields.append('description')
            runtime = (
                local_item.get('runtime') or turkish_item.get('runtime')
                or english_item.get('runtime')
            )
            if runtime and episode.duration_minutes != int(runtime):
                episode.duration_minutes = int(runtime)
                episode_fields.append('duration_minutes')
            air_date = parse_date(
                local_item.get('air_date') or turkish_item.get('air_date')
                or english_item.get('air_date') or ''
            )
            if air_date and episode.air_date != air_date:
                episode.air_date = air_date
                episode_fields.append('air_date')
            still_path = (
                local_item.get('still_path') or turkish_item.get('still_path')
                or english_item.get('still_path')
            )
            if still_path and not episode.poster:
                art_fields = attach_tmdb_artwork(
                    episode,
                    {
                        'id': local_item.get('id') or turkish_item.get('id') or english_item.get('id'),
                        'poster_path': still_path,
                    },
                    prefix=f'esref-s{season_number}-e{episode.episode_number}',
                    allow_poster_backdrop=False,
                )
                episode_fields.extend(art_fields)
                episode_artwork += int(bool(art_fields))
            if episode_fields:
                episode.save(update_fields=[*dict.fromkeys(episode_fields), 'updated_at'])
                metadata_updates += 1
    print(
        f'  tmdb season/episode metadata rows_updated={metadata_updates} '
        f'episode_artwork={episode_artwork}',
        flush=True,
    )

    if not args.skip_softsub:
        try:
            from django.core.cache import cache
            from apps.catalog.tasks import _softsub_queue_lock
            cache.delete(_softsub_queue_lock('series', series.pk))
        except Exception as exc:  # noqa: BLE001
            print(f'  softsub lock clear warn: {exc}', flush=True)
        queued = enqueue_series_softsub(series.pk, force=False, episode_limit=60)
        print(f'  softsub_queued={queued}', flush=True)

    try:
        bump_catalog_cache_version()
    except Exception as exc:  # noqa: BLE001
        print(f'cache bump warn: {exc}', flush=True)

    series.refresh_from_db()
    print(
        f'\nDONE series pk={series.pk} slug={series.slug} title={series.title!r} '
        f'dub={series.is_dubbed} has_sub={series.has_subtitle} url=/series/{series.slug}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
