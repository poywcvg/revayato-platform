"""Language-aware ranking helpers for public catalog search."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


_ARABIC_TO_PERSIAN = str.maketrans({
    'ي': 'ی',
    'ى': 'ی',
    'ك': 'ک',
    'ؤ': 'و',
    'ئ': 'ی',
    'ء': '',
    'أ': 'ا',
    'إ': 'ا',
    'آ': 'ا',
})
_DIACRITICS_RE = re.compile(r'[\u064b-\u065f\u0670]')
_SEPARATORS_RE = re.compile(r'[\W_]+', flags=re.UNICODE)
_SEARCH_DIGIT_TRANSLATION = str.maketrans({
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
})
_YEAR_RE = re.compile(r'(?<!\d)(?:1[89]\d{2}|20\d{2}|2100)(?!\d)')
_YEAR_ONLY_WORDS = {
    'سال', 'محصول', 'انتشار', 'سال انتشار',
    'year', 'release', 'released', 'release year',
}


@dataclass(frozen=True)
class ParsedSearchQuery:
    """The title/person part and optional release year entered in one field."""

    text: str
    year: int | None


def normalize_search_digits(value: str) -> str:
    """Convert Persian and Arabic-Indic digits to their database form."""
    return str(value or '').translate(_SEARCH_DIGIT_TRANSLATION)


def parse_search_query(value: str) -> ParsedSearchQuery:
    """Extract a standalone catalog year from a free-text search query.

    This intentionally accepts release years only (1888–2100), so ordinary
    numbers in titles are left untouched. The final valid year is used, which
    makes inputs such as ``Dune (2021)`` and ``تلماسه ۲۰۲۱`` predictable.
    """
    with_ascii_digits = normalize_search_digits(value).strip()
    matches = [
        match for match in _YEAR_RE.finditer(with_ascii_digits)
        if 1888 <= int(match.group(0)) <= 2100
    ]
    if not matches:
        return ParsedSearchQuery(text=with_ascii_digits, year=None)

    match = matches[-1]
    year = int(match.group(0))
    text = f'{with_ascii_digits[:match.start()]} {with_ascii_digits[match.end():]}'
    text = re.sub(r'[()\[\]{},،:؛|/\\\-–—]+', ' ', text)
    text = ' '.join(text.split())
    if normalize_search_text(text) in _YEAR_ONLY_WORDS:
        text = ''
    return ParsedSearchQuery(text=text, year=year)


def normalize_search_text(value: str) -> str:
    """Normalize Persian/Arabic variants and punctuation without losing words."""
    normalized = unicodedata.normalize('NFKC', normalize_search_digits(value))
    normalized = normalized.translate(_ARABIC_TO_PERSIAN)
    normalized = _DIACRITICS_RE.sub('', normalized)
    normalized = normalized.replace('\u200c', ' ').replace('\u200d', ' ')
    normalized = _SEPARATORS_RE.sub(' ', normalized.casefold())
    return ' '.join(normalized.split())


def search_query_variants(value: str) -> tuple[str, ...]:
    """Return safe database probes for common Persian keyboard variants."""
    raw = ' '.join(str(value or '').split())
    normalized = normalize_search_text(raw)
    variants = {candidate for candidate in (raw, normalized) if candidate}
    if normalized:
        variants.add(normalized.translate(str.maketrans({'ی': 'ي', 'ک': 'ك'})))
    return tuple(variants)


def title_search_q(value: str):
    """Precise title/slug match: full-string variants OR every token across title fields."""
    from django.db.models import Q

    variants = search_query_variants(value)
    fields = ('title', 'original_title', 'slug')
    combined = Q()
    for variant in variants:
        for field in fields:
            combined |= Q(**{f'{field}__icontains': variant})

    tokens = [
        token
        for token in normalize_search_text(value).split()
        if len(token) >= 2
    ]
    if len(tokens) >= 2:
        token_and = Q()
        first = True
        for token in tokens:
            token_or = Q()
            for field in fields:
                token_or |= Q(**{f'{field}__icontains': token})
            if first:
                token_and = token_or
                first = False
            else:
                token_and &= token_or
        combined |= token_and
    return combined


def broad_search_q(value: str):
    """Fallback probes across synopsis / people / genres when titles miss."""
    from django.db.models import Q

    variants = search_query_variants(value)
    fields = (
        'short_description',
        'description',
        'genres__title',
        'actors__name',
        'actors__original_name',
        'directors__name',
        'directors__original_name',
    )
    combined = Q()
    for variant in variants:
        for field in fields:
            combined |= Q(**{f'{field}__icontains': variant})
    return combined


def title_rank_annotation(query: str):
    """Build a Case/When rank that respects Persian/Arabic keyboard variants."""
    from django.db.models import Case, IntegerField, Value, When

    variants = search_query_variants(query)
    whens: list = []
    for variant in variants:
        whens.extend([
            When(title__iexact=variant, then=Value(100)),
            When(original_title__iexact=variant, then=Value(98)),
            When(slug__iexact=variant, then=Value(96)),
            When(title__istartswith=variant, then=Value(88)),
            When(original_title__istartswith=variant, then=Value(84)),
            When(slug__istartswith=variant, then=Value(80)),
            When(title__icontains=variant, then=Value(70)),
            When(original_title__icontains=variant, then=Value(66)),
            When(slug__icontains=variant, then=Value(62)),
        ])
    tokens = [token for token in normalize_search_text(query).split() if len(token) >= 2]
    if len(tokens) >= 2:
        for token in tokens:
            whens.extend([
                When(title__icontains=token, then=Value(58)),
                When(original_title__icontains=token, then=Value(56)),
                When(slug__icontains=token, then=Value(54)),
            ])
    return Case(*whens, default=Value(25), output_field=IntegerField())


def _compact(value: str) -> str:
    return normalize_search_text(value).replace(' ', '')


def _dice_similarity(left: str, right: str) -> float:
    left = _compact(left)
    right = _compact(right)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if len(left) == 1 or len(right) == 1:
        return 0.5 if left in right or right in left else 0.0

    left_pairs: dict[str, int] = {}
    right_pairs: dict[str, int] = {}
    for index in range(len(left) - 1):
        pair = left[index:index + 2]
        left_pairs[pair] = left_pairs.get(pair, 0) + 1
    for index in range(len(right) - 1):
        pair = right[index:index + 2]
        right_pairs[pair] = right_pairs.get(pair, 0) + 1

    overlap = sum(
        min(count, right_pairs.get(pair, 0))
        for pair, count in left_pairs.items()
    )
    return (2 * overlap) / (len(left) - 1 + len(right) - 1)


def _title_score(query: str, title: str) -> tuple[float, bool]:
    query_normalized = normalize_search_text(query)
    title_normalized = normalize_search_text(title)
    if not query_normalized or not title_normalized:
        return 0.0, False

    query_compact = query_normalized.replace(' ', '')
    title_compact = title_normalized.replace(' ', '')
    if query_normalized == title_normalized or query_compact == title_compact:
        return 1.0, True

    sequence = SequenceMatcher(None, query_compact, title_compact).ratio()
    dice = _dice_similarity(query_normalized, title_normalized)
    query_tokens = set(query_normalized.split())
    title_tokens = set(title_normalized.split())
    token_coverage = (
        len(query_tokens & title_tokens) / len(query_tokens)
        if query_tokens else 0.0
    )
    containment = 0.82 if query_compact in title_compact or title_compact in query_compact else 0.0
    return max(sequence, dice, containment, (sequence * 0.72) + (token_coverage * 0.28)), False


def rank_similar_title_ids(queryset, query: str, limit: int) -> tuple[list[int], bool]:
    """Rank typo-tolerant title candidates without loading the whole catalog.

    PostgreSQL first uses the functional ``pg_trgm`` indexes installed by the
    catalog migration.  Python then applies the language-aware scorer only to
    that small candidate set.  SQLite keeps the full-scan fallback for tests
    and local development, where the catalog is intentionally tiny.

    The returned boolean reports whether normalization found an exact title
    (for example Persian/Arabic keyboard variants that SQL ``icontains`` missed).
    """
    from django.db import connection

    candidate_queryset = queryset
    if connection.vendor == 'postgresql':
        from django.contrib.postgres.search import TrigramSimilarity
        from django.db.models import Q, Value
        from django.db.models.functions import Greatest, Upper

        # The migration indexes UPPER(title/original_title/slug), so keep the
        # lookup expression identical.  ``__trigram_similar`` lets PostgreSQL
        # use the GIN indexes instead of calculating similarity for every row.
        probe = normalize_search_text(query).upper()
        candidate_limit = max(32, min(240, limit * 8))
        candidate_queryset = (
            queryset
            .alias(
                _search_title=Upper('title'),
                _search_original_title=Upper('original_title'),
                _search_slug=Upper('slug'),
            )
            .filter(
                Q(_search_title__trigram_similar=probe)
                | Q(_search_original_title__trigram_similar=probe)
                | Q(_search_slug__trigram_similar=probe)
            )
            .annotate(
                _trigram_score=Greatest(
                    TrigramSimilarity(Upper('title'), Value(probe)),
                    TrigramSimilarity(Upper('original_title'), Value(probe)),
                    TrigramSimilarity(Upper('slug'), Value(probe)),
                ),
            )
            .order_by('-_trigram_score', '-popularity', '-view_count')[:candidate_limit]
        )

    ranked: list[tuple[float, float, int, bool]] = []
    for row in candidate_queryset.values(
        'id', 'title', 'original_title', 'popularity', 'view_count',
    ):
        title_scores = [
            _title_score(query, row.get('title') or ''),
            _title_score(query, row.get('original_title') or ''),
        ]
        score, normalized_exact = max(title_scores, key=lambda item: item[0])
        if score <= 0:
            continue
        popularity = float(row.get('popularity') or 0)
        engagement = min(float(row.get('view_count') or 0), 1_000_000) / 1_000_000
        ranked.append((score, popularity + engagement, row['id'], normalized_exact))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not ranked:
        return [], False

    compact_length = len(_compact(query))
    threshold = 0.68 if compact_length <= 3 else 0.48 if compact_length <= 6 else 0.38
    # Keep alternatives close to the best candidate as well as above the
    # absolute floor. This prevents coincidental shared letters from turning
    # an obvious typo match into a noisy list of unrelated titles.
    relative_floor = ranked[0][0] * 0.72
    credible = [item for item in ranked if item[0] >= max(threshold, relative_floor)]

    # A long query with a shared title token often identifies another entry in
    # the same franchise (for example a sequel that is not in the catalog).
    if not credible and len(normalize_search_text(query).split()) >= 2:
        credible = [item for item in ranked if item[0] >= 0.28]

    selected = credible[:limit]
    return [item[2] for item in selected], any(item[3] for item in selected)
