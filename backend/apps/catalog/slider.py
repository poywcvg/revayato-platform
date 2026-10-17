"""Admin-curated home slider shared by the website and the application.

Membership is the existing ``is_featured`` flag on :class:`Movie` / :class:`Series`
— the same toggle the admin panel already offers — plus two new columns:

* ``featured_order`` — lower shows first; ties fall back to recency.
* ``slider_platform`` — ``all`` (default) feeds both clients, ``web`` / ``app``
  target one. The default keeps a single admin choice visible everywhere, which
  is what "one slider for the site and the app" means without duplicating rows.

Both clients read the same ordered list; the only difference is the
``platform`` filter (``web`` for the Nuxt front, ``app`` for Android).
Unfiltered (no platform) returns everything, so existing callers that never
pass a platform keep working.
"""

from __future__ import annotations


def slider_platforms(platform: str | None) -> list[str]:
    """Platform values visible to ``platform`` (``all`` always included)."""
    from apps.catalog.models import SliderPlatform

    wanted = str(platform or '').strip().lower()
    if wanted == SliderPlatform.WEB:
        return [SliderPlatform.ALL, SliderPlatform.WEB]
    if wanted == SliderPlatform.APP:
        return [SliderPlatform.ALL, SliderPlatform.APP]
    return [SliderPlatform.ALL, SliderPlatform.WEB, SliderPlatform.APP]


def slider_queryset(model, *, platform: str | None = None, limit: int = 24):
    """Published featured rows for ``platform``, admin order first."""
    from apps.catalog.models import Movie

    limit = max(1, min(int(limit or 24), 30))
    if model is Movie:
        prefetch = ('genres', 'countries', 'directors', 'movie_actors__actor')
    else:
        prefetch = ('genres', 'countries', 'directors', 'series_actors__actor')
    return (
        model.objects.filter(
            is_published=True,
            is_featured=True,
            slider_platform__in=slider_platforms(platform),
        )
        .prefetch_related(*prefetch)
        .order_by('featured_order', '-updated_at', '-id')[:limit]
    )


def slider_items(*, platform: str | None = None, limit: int = 24) -> list[dict]:
    """Merged movies + series slider, admin order first (stable across types).

    Rows are interleaved by ``(featured_order, updated_at, id)`` so an admin
    ordering of 1..N reads the same on both clients regardless of type. Each
    entry is ``{'content_type': 'movie'|'series', 'movie'|'series': obj}``.
    """
    from apps.catalog.models import Movie, Series

    limit = max(1, min(int(limit or 24), 30))
    movies = list(slider_queryset(Movie, platform=platform, limit=limit))
    series = list(slider_queryset(Series, platform=platform, limit=limit))

    merged: list[tuple[tuple, str, object]] = []
    for obj in movies:
        updated = getattr(obj, 'updated_at', None)
        try:
            stamp = -updated.timestamp() if updated is not None else 0.0
        except (AttributeError, OSError, OverflowError):
            stamp = 0.0
        merged.append(((int(getattr(obj, 'featured_order', 0) or 0), stamp, -int(obj.pk)), 'movie', obj))
    for obj in series:
        updated = getattr(obj, 'updated_at', None)
        try:
            stamp = -updated.timestamp() if updated is not None else 0.0
        except (AttributeError, OSError, OverflowError):
            stamp = 0.0
        merged.append(((int(getattr(obj, 'featured_order', 0) or 0), stamp, -int(obj.pk)), 'series', obj))
    merged.sort(key=lambda row: row[0])
    return [
        {'content_type': kind, kind: obj} for _, kind, obj in merged[:limit]
    ]
