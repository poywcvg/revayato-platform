"""English (ASCII) addresses for movie and series pages.

A page address is built from the English title plus the year —
``/movies/inception-2010/`` — never from the Persian title. Addresses that were
Persian before this change keep working: every time a row's slug changes the old
one is kept in :class:`~apps.catalog.models.CatalogSlugAlias`, the API resolves it
through :func:`canonical_slug`, and the web app answers it with a 301 to the new
address. Links already shared, bookmarked or indexed therefore never break.
"""

from __future__ import annotations

import re

from django.utils.text import slugify

_ENGLISH_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
MAX_BASE_LENGTH = 200


def is_english_slug(value: str | None) -> bool:
    return bool(value) and bool(_ENGLISH_SLUG_RE.match(value))


def english_slug_base(*titles, year=None, fallback: str = 'item') -> str:
    """``inception-2010`` from the first title that has Latin letters.

    ``slugify(allow_unicode=False)`` decomposes accents (``Amélie`` → ``amelie``)
    and drops every non-ASCII letter, so a Persian or Japanese title yields
    nothing and the next candidate is tried.
    """
    base = ''
    for title in titles:
        base = slugify(str(title or ''), allow_unicode=False)[:MAX_BASE_LENGTH].strip('-')
        if base:
            break
    if not base:
        return fallback
    year = str(year or '').strip()
    if year.isdigit() and len(year) == 4 and not base.endswith(f'-{year}'):
        base = f'{base}-{year}'
    return base


def unique_english_slug(model, base: str, *, suffix=None, current_pk=None) -> str:
    """``base``; ``base-<suffix>`` when another row holds it; then numbered."""

    def taken(candidate):
        qs = model.objects.filter(slug=candidate)
        if current_pk:
            qs = qs.exclude(pk=current_pk)
        return qs.exists()

    if not taken(base):
        return base
    if suffix:
        candidate = f'{base}-{suffix}'
        if not taken(candidate):
            return candidate
    index = 2
    while taken(f'{base}-{index}'):
        index += 1
    return f'{base}-{index}'


def english_slug_for(model, *, title='', original_title='', year=None, tmdb_id=None,
                     current_pk=None, current_slug='') -> str:
    """The address a row should have: its current one if already English."""
    if is_english_slug(current_slug):
        return current_slug
    kind = 'series' if model._meta.model_name == 'series' else 'movie'
    fallback = f'{kind}-{tmdb_id}' if tmdb_id else kind
    base = english_slug_base(original_title, title, year=year, fallback=fallback)
    return unique_english_slug(model, base, suffix=tmdb_id, current_pk=current_pk)


def _kind(model) -> str:
    return 'series' if model._meta.model_name == 'series' else 'movie'


def canonical_slug(model, slug: str) -> str:
    """The live slug for ``slug``: itself if a row has it, else its alias target.

    Unknown slugs are returned unchanged so the caller's normal 404 applies.
    """
    if not slug or model.objects.filter(slug=slug).exists():
        return slug
    from apps.catalog.models import CatalogSlugAlias

    alias = CatalogSlugAlias.objects.filter(kind=_kind(model), old_slug=slug).only('object_id').first()
    if alias is None:
        return slug
    current = model.objects.filter(pk=alias.object_id).values_list('slug', flat=True).first()
    return current or slug


def remember_old_slug(model, *, object_id: int, old_slug: str, new_slug: str) -> None:
    """Keep ``old_slug`` pointing at the row; the new slug is live, so drop its alias."""
    from apps.catalog.models import CatalogSlugAlias

    kind = _kind(model)
    CatalogSlugAlias.objects.filter(kind=kind, old_slug=new_slug).delete()
    if old_slug and old_slug != new_slug:
        CatalogSlugAlias.objects.update_or_create(
            kind=kind, old_slug=old_slug, defaults={'object_id': object_id},
        )


def _track_slug_change(sender, instance, update_fields=None, **kwargs):
    if not instance.pk or (update_fields is not None and 'slug' not in update_fields):
        return
    old = sender.objects.filter(pk=instance.pk).values_list('slug', flat=True).first()
    instance._slug_before_save = old


def _record_slug_change(sender, instance, created=False, update_fields=None, **kwargs):
    old = getattr(instance, '_slug_before_save', None)
    instance._slug_before_save = None
    if created or not old or old == instance.slug:
        return
    remember_old_slug(sender, object_id=instance.pk, old_slug=old, new_slug=instance.slug)


def connect_slug_signals():
    from django.db.models.signals import post_save, pre_save

    from apps.catalog.models import Movie, Series

    for model in (Movie, Series):
        pre_save.connect(_track_slug_change, sender=model, dispatch_uid=f'slug-track-{model.__name__}')
        post_save.connect(_record_slug_change, sender=model, dispatch_uid=f'slug-record-{model.__name__}')
