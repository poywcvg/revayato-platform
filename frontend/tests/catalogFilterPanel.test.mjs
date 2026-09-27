import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const browser = readFileSync(
  new URL('../app/components/content/CatalogBrowser.vue', import.meta.url),
  'utf8',
)
const fields = readFileSync(
  new URL('../app/components/content/CatalogFilterFields.vue', import.meta.url),
  'utf8',
)
const nav = readFileSync(
  new URL('../app/components/layout/HeaderNavGenre.vue', import.meta.url),
  'utf8',
)

// A "genre page" is not a route of its own: the header menu links into the
// ordinary catalog with the genre pinned in the query string. Whatever arrives
// pre-filtered that way has to show the filters it arrived with.

test('the genre menu lands on the catalog with the genre in the query', () => {
  assert.match(nav, /path: group\.path[\s\S]{0,120}genre: genre\.slug/)
})

test('a URL that arrives pre-filtered opens the filter panel', () => {
  assert.match(browser, /const panelOpen = ref\(props\.discovery \|\| hasRefinementFilters\.value\)/)
  // Seeded once from the arrival state. A computed here would re-open the panel
  // under the viewer every time a filter changed, and closing it would be
  // impossible while any filter was set.
  assert.doesNotMatch(browser, /const panelOpen = computed\(/)
})

test('a bare search is not a refinement, so it does not force the panel open', () => {
  assert.match(
    browser,
    /hasRefinementFilters = computed\(\(\) => activeFilterChips\.value\.some\(chip => chip\.key !== "query"\)\)/,
  )
})

test('the panel carries the full field set, genre included', () => {
  assert.match(browser, /v-show="panelOpen"[\s\S]{0,200}<CatalogFilterFields/)
  assert.match(browser, /<CatalogFilterFields[\s\S]{0,400}:genres="genres"/)
  for (const field of ['country', 'year', 'language', 'ageRating', 'availability', 'format', 'minRating']) {
    assert.match(fields, new RegExp(`key: '${field}'`), `${field} missing from the panel`)
  }
  assert.match(fields, /<GenreChips[\s\S]{0,200}:model-value="filters\.genre"/)
})

test('an applied genre stays visible and removable as a chip', () => {
  assert.match(browser, /key: "genre",[\s\S]{0,160}genres\.value\.find\(\(genre\) => genre\.slug === filters\.genre\)\?\.title/)
  assert.match(browser, /v-for="chip in activeFilterChips"[\s\S]{0,400}removeFilter\(chip\.key\)/)
})
