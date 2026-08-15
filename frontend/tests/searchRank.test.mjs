import assert from 'node:assert/strict'
import test from 'node:test'

import { parseSearchQuery, rankCatalogSearch } from '../app/utils/searchRank.ts'

function movie(id, title, year) {
  return {
    id,
    title,
    secondary_title: '',
    original_title: title,
    slug: `${title.toLowerCase()}-${year}`,
    year,
    director: '',
    cast: [],
    genres: [],
    type: 'movie',
    format: 'live_action',
    popularity: 50,
    rating: 8,
  }
}

test('extracts a release year written with Persian digits', () => {
  assert.deepEqual(parseSearchQuery('Dune (۲۰۲۱)'), { text: 'Dune', year: 2021 })
  assert.deepEqual(parseSearchQuery('سال ۲۰۲۴'), { text: '', year: 2024 })
})

test('a year-only query returns only catalog items from that year', () => {
  const results = rankCatalogSearch([
    movie(1, 'Dune', 2021),
    movie(2, 'Dune', 1984),
    movie(3, 'Arrival', 2016),
  ], '۲۰۲۱')

  assert.deepEqual(results.map(hit => hit.item.id), [1])
})

test('a title and year query selects the matching edition', () => {
  const results = rankCatalogSearch([
    movie(1, 'Dune', 1984),
    movie(2, 'Dune', 2021),
  ], 'Dune 2021')

  assert.deepEqual(results.map(hit => hit.item.id), [2])
  assert.equal(results[0].kind, 'exact')
})
