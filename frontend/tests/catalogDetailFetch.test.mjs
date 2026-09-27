import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const useContent = readFileSync(new URL('../app/composables/content/useContent.ts', import.meta.url), 'utf8')

test('detail pages fetch the full DTO even when a lean catalog card is cached', () => {
  const helper = useContent.slice(useContent.indexOf('export function useMovieBySlug'))

  assert.match(helper, /expectedType\s*\?\s*loadItemFromApi\(toValue\(slug\), expectedType\)/)
  assert.doesNotMatch(helper, /movie\.value\s*\?\s*Promise\.resolve\(movie\.value\)/)
})
