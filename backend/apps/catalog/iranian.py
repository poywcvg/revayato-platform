"""Detect Iranian cinema/TV so the Hollywood-only crawler can skip or purge it."""

from __future__ import annotations

IRANIAN_LANGUAGE_CODES = frozenset({'fa', 'per', 'fas'})
IRAN_COUNTRY_CODE = 'IR'


def _norm_lang(value) -> str:
    return str(value or '').strip().lower()


def _norm_country(value) -> str:
    return str(value or '').strip().upper()[:2]


def is_iranian_tmdb_details(details: dict | None) -> bool:
    """True when TMDB payload is Iranian by language or production/origin country."""
    payload = details or {}
    if _norm_lang(payload.get('original_language')) in IRANIAN_LANGUAGE_CODES:
        return True
    for item in payload.get('production_countries') or []:
        if isinstance(item, dict):
            if _norm_country(item.get('iso_3166_1')) == IRAN_COUNTRY_CODE:
                return True
        elif _norm_country(item) == IRAN_COUNTRY_CODE:
            return True
    for code in payload.get('origin_country') or []:
        if _norm_country(code) == IRAN_COUNTRY_CODE:
            return True
    return False


def is_iranian_catalog_item(obj) -> bool:
    """True for a Movie/Series row that looks Iranian."""
    if obj is None:
        return False
    if _norm_lang(getattr(obj, 'original_language', '')) in IRANIAN_LANGUAGE_CODES:
        return True

    countries = getattr(obj, 'countries', None)
    if countries is not None:
        try:
            if countries.filter(code__iexact=IRAN_COUNTRY_CODE).exists():
                return True
        except Exception:
            pass

    meta = getattr(obj, 'source_metadata', None) or {}
    if isinstance(meta, dict) and is_iranian_tmdb_details(meta):
        return True
    return False


def iranian_movie_queryset(qs=None):
    from apps.catalog.models import Movie

    base = qs if qs is not None else Movie.objects.all()
    return base.filter(
        models_Q_iranian(),
    )


def iranian_series_queryset(qs=None):
    from apps.catalog.models import Series

    base = qs if qs is not None else Series.objects.all()
    return base.filter(
        models_Q_iranian(),
    )


def models_Q_iranian():
    from django.db.models import Q

    return (
        Q(original_language__iexact='fa')
        | Q(original_language__iexact='per')
        | Q(original_language__iexact='fas')
        | Q(countries__code__iexact=IRAN_COUNTRY_CODE)
    )
