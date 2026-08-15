import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const slider = readFileSync(new URL('../app/components/home/HeroMovieSlider.vue', import.meta.url), 'utf8')
const thumbnails = readFileSync(new URL('../app/components/home/HeroMovieThumb.vue', import.meta.url), 'utf8')

test('header artwork stays sharp and has no image shade or blur layer', () => {
  assert.doesNotMatch(slider, /hero-movie-slider__edge-blur/)
  assert.doesNotMatch(slider, /filter:\s*saturate/)
  assert.match(slider, /hero-movie-slider__backdrop-image[\s\S]*?filter:\s*none/)
  assert.doesNotMatch(thumbnails, /hero-movie-thumb__shade/)
  assert.doesNotMatch(thumbnails, /filter:\s*brightness/)
  assert.match(thumbnails, /hero-movie-thumb__poster[\s\S]*?box-shadow:\s*none/)
  assert.match(thumbnails, /quality="86"/)
})
