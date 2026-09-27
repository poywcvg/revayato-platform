import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

const utilityUrl = new URL('../app/utils/routeSlug.ts', import.meta.url)

test('route slug decoder normalizes SSR-encoded Persian params', async () => {
  const source = await readFile(utilityUrl, 'utf8')
  const executable = source.replace(/export function decodeRouteSlug\(value: unknown\): string/, 'function decodeRouteSlug(value)')
  const decodeRouteSlug = new Function(`${executable}; return decodeRouteSlug`)()
  const slug = 'آزادکار-1367922'
  assert.equal(decodeRouteSlug(encodeURIComponent(slug)), slug)
  assert.equal(decodeRouteSlug(slug), slug)
  assert.equal(decodeRouteSlug('%E0%A4%A'), '%E0%A4%A')
})

test('detail pages normalize params before API lookup', async () => {
  for (const path of ['../app/pages/movies/[slug].vue', '../app/pages/series/[slug].vue']) {
    const source = await readFile(new URL(path, import.meta.url), 'utf8')
    assert.match(source, /decodeRouteSlug\(route\.params\.slug\)/)
  }
})
