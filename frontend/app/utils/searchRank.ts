import type { Movie } from '~/types'

export type SearchMatchKind = 'exact' | 'prefix' | 'contains' | 'similar'

export interface RankedSearchHit {
  item: Movie
  score: number
  kind: SearchMatchKind
}

export interface ParsedSearchQuery {
  text: string
  year?: number
}

const searchDigitMap: Record<string, string> = {
  '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
  '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
  '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
  '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
}

export function normalizeSearchDigits(value: string) {
  return String(value || '').replace(/[۰-۹٠-٩]/g, digit => searchDigitMap[digit] || digit)
}

export function parseSearchQuery(value: string): ParsedSearchQuery {
  const normalizedDigits = normalizeSearchDigits(value).trim()
  const yearPattern = /(^|\D)((?:1[89]\d{2}|20\d{2}|2100))(?!\d)/g
  let parsedYear: { value: number; index: number; length: number } | undefined
  for (const match of normalizedDigits.matchAll(yearPattern)) {
    const year = Number(match[2])
    if (year < 1888 || year > 2100 || match.index === undefined) continue
    parsedYear = {
      value: year,
      index: match.index + (match[1]?.length || 0),
      length: match[2]?.length || 0,
    }
  }
  if (!parsedYear) return { text: normalizedDigits }

  const text = `${normalizedDigits.slice(0, parsedYear.index)} ${normalizedDigits.slice(parsedYear.index + parsedYear.length)}`
    .replace(/[()[\]{},،:؛|/\\\-–—]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  const normalizedText = normalizeSearchText(text)
  const yearOnlyWords = new Set([
    'سال', 'محصول', 'انتشار', 'سال انتشار',
    'year', 'release', 'released', 'release year',
  ])
  return { text: yearOnlyWords.has(normalizedText) ? '' : text, year: parsedYear.value }
}

export function normalizeSearchText(value: string) {
  return normalizeSearchDigits(value)
    .normalize('NFKC')
    .replace(/[يى]/g, 'ی')
    .replace(/ك/g, 'ک')
    .replace(/[ؤئءأإآ]/g, (ch) => ({
      'ؤ': 'و',
      'ئ': 'ی',
      'ء': '',
      'أ': 'ا',
      'إ': 'ا',
      'آ': 'ا',
    }[ch] || ch))
    .replace(/[\u064B-\u065F\u0670]/g, '')
    .replace(/[\u200C\u200D]/g, ' ')
    .replace(/[_.,:;!?/\\|+=*()[\]{}«»"'`~@#$%^&-]+/g, ' ')
    .toLocaleLowerCase('fa')
    .replace(/\s+/g, ' ')
    .trim()
}

function compactText(value: string) {
  return normalizeSearchText(value).replace(/\s+/g, '')
}

/** Dice coefficient over character bigrams — works well for short Persian/English titles. */
export function stringSimilarity(a: string, b: string) {
  const left = compactText(a)
  const right = compactText(b)
  if (!left || !right) return 0
  if (left === right) return 1
  if (left.length === 1 || right.length === 1) return left.includes(right) || right.includes(left) ? 0.5 : 0

  const bigrams = (value: string) => {
    const map = new Map<string, number>()
    for (let index = 0; index < value.length - 1; index += 1) {
      const gram = value.slice(index, index + 2)
      map.set(gram, (map.get(gram) || 0) + 1)
    }
    return map
  }

  const aGrams = bigrams(left)
  const bGrams = bigrams(right)
  let overlap = 0
  for (const [gram, count] of aGrams) {
    const other = bGrams.get(gram)
    if (other) overlap += Math.min(count, other)
  }
  return (2 * overlap) / (left.length - 1 + right.length - 1)
}

function titleCandidates(item: Movie) {
  return [item.title, item.secondary_title || '', item.original_title].filter(Boolean)
}

function searchableBlob(item: Movie) {
  return normalizeSearchText([
    ...titleCandidates(item),
    item.director,
    item.cast.map(person => `${person.name} ${person.secondary_name || ''}`).join(' '),
    item.genres.map(genre => genre.title).join(' '),
    item.type === 'movie' ? 'فیلم' : 'سریال',
    item.format === 'animation' ? 'انیمیشن' : '',
    item.year,
  ].join(' '))
}

function bestTitleSimilarity(item: Movie, query: string) {
  return Math.max(0, ...titleCandidates(item).map(title => stringSimilarity(title, query)))
}

export function scoreCatalogItem(item: Movie, query: string): RankedSearchHit | null {
  const parsedQuery = parseSearchQuery(query)
  const normalizedQuery = normalizeSearchText(parsedQuery.text)
  if (parsedQuery.year && item.year !== parsedQuery.year) return null
  if (!normalizedQuery) {
    if (!parsedQuery.year) return null
    return {
      item,
      score: 700 + Math.min(8, item.popularity / 40) + (item.rating || 0),
      kind: 'contains',
    }
  }

  const tokens = normalizedQuery.split(' ').filter(Boolean)
  const titles = titleCandidates(item).map(normalizeSearchText)
  const compactQuery = compactText(normalizedQuery)
  const blob = searchableBlob(item)
  const popularityBoost = Math.min(8, item.popularity / 40)
  const ratingBoost = item.rating ? item.rating : 0
  const yearBoost = parsedQuery.year ? 80 : 0

  // Exact title match
  if (titles.some(title => title === normalizedQuery || compactText(title) === compactQuery)) {
    return { item, score: 1000 + yearBoost + popularityBoost + ratingBoost, kind: 'exact' }
  }

  // Prefix on any title
  if (titles.some(title => title.startsWith(normalizedQuery) || compactText(title).startsWith(compactQuery))) {
    return { item, score: 820 + yearBoost + popularityBoost + ratingBoost, kind: 'prefix' }
  }

  // All query tokens present in titles
  if (tokens.length && titles.some(title => tokens.every(token => title.includes(token)))) {
    return { item, score: 720 + yearBoost + popularityBoost + ratingBoost, kind: 'contains' }
  }

  // All tokens somewhere in searchable fields
  if (tokens.length && tokens.every(token => blob.includes(token))) {
    const titleHit = titles.some(title => tokens.some(token => title.includes(token)))
    return {
      item,
      score: (titleHit ? 560 : 420) + yearBoost + popularityBoost + ratingBoost,
      kind: 'contains',
    }
  }

  // Fuzzy / similar titles (typos, close names)
  const similarity = bestTitleSimilarity(item, normalizedQuery)
  const minSimilarity = normalizedQuery.length <= 3 ? 0.72 : normalizedQuery.length <= 6 ? 0.55 : 0.45
  if (similarity >= minSimilarity) {
    return {
      item,
      score: 280 + similarity * 200 + yearBoost + popularityBoost + ratingBoost,
      kind: 'similar',
    }
  }

  // Partial token overlap on titles for longer queries
  if (tokens.length >= 2) {
    const titleTokenHits = tokens.filter(token => titles.some(title => title.includes(token))).length
    if (titleTokenHits / tokens.length >= 0.5) {
      return {
        item,
        score: 240 + titleTokenHits * 40 + yearBoost + popularityBoost,
        kind: 'similar',
      }
    }
  }

  return null
}

export function rankCatalogSearch(
  catalog: readonly Movie[],
  query: string,
  options: { limit?: number; includeSimilar?: boolean } = {},
): RankedSearchHit[] {
  const limit = options.limit ?? 8
  const includeSimilar = options.includeSimilar !== false
  const normalizedQuery = normalizeSearchText(query)
  if (!normalizedQuery) return []

  const hits = catalog
    .map(item => scoreCatalogItem(item, normalizedQuery))
    .filter((hit): hit is RankedSearchHit => Boolean(hit))
    .sort((a, b) => b.score - a.score || b.item.popularity - a.item.popularity)

  const exactish = hits.filter(hit => hit.kind !== 'similar')
  if (exactish.length >= 3 || !includeSimilar) {
    return (exactish.length ? exactish : hits).slice(0, limit)
  }

  // Prefer direct matches first, then fill with similar titles.
  const similar = hits.filter(hit => hit.kind === 'similar')
  return [...exactish, ...similar].slice(0, limit)
}

export function detailPathForMovie(item: Pick<Movie, 'type' | 'slug'>) {
  return `/${item.type === 'movie' ? 'movies' : 'series'}/${item.slug}`
}
