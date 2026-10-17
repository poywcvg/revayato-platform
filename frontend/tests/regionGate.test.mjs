import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { countryFromTrace, persianCountryName } from '../app/composables/useViewerRegion.ts'

const composable = readFileSync(
  new URL('../app/composables/useViewerRegion.ts', import.meta.url),
  'utf8',
)
const modal = readFileSync(
  new URL('../app/components/content/RegionPlaybackModal.vue', import.meta.url),
  'utf8',
)
const watchPage = readFileSync(
  new URL('../app/pages/watch/[slug].vue', import.meta.url),
  'utf8',
)

test('the country is read out of the edge trace body', () => {
  const body = 'fl=997f47\nh=revayato.com\nip=2a10:4640::1\nvisit_scheme=https\nloc=FR\ntls=TLSv1.3\n'
  assert.equal(countryFromTrace(body), 'FR')
  // `loc` is matched as its own line, so neither `colo` nor a stray substring
  // of another key can be mistaken for it.
  assert.equal(countryFromTrace('colo=AMS\nloc=ir\n'), 'IR')
  assert.equal(countryFromTrace('sliver=010-tier1\ncolo=AMS\n'), '')
})

test('an unresolved country is never reported as a country', () => {
  // Cloudflare answers XX when it has no country for the address and T1 for a
  // Tor exit. Neither says the viewer is abroad, so neither may block.
  assert.equal(countryFromTrace('loc=XX\n'), '')
  assert.equal(countryFromTrace('loc=T1\n'), '')
  assert.equal(countryFromTrace(''), '')
  assert.equal(countryFromTrace(undefined), '')
})

test('the country is named in the viewer’s own language', () => {
  // Persian script, so the modal reads as one sentence rather than a code the
  // viewer has to decode.
  assert.match(persianCountryName('FR'), /[\u0600-\u06FF]/)
  assert.match(persianCountryName('DE'), /[\u0600-\u06FF]/)
  // Nothing resolved: the modal drops the line entirely rather than naming a
  // placeholder country.
  assert.equal(persianCountryName(''), '')
})

test('a failed lookup leaves the viewer unclaimed rather than abroad', () => {
  // Both probes swallow their failure and fall through to the untouched state:
  // nothing resolved a country, so nothing is said.
  assert.match(composable, /status: 'unknown', country: ''/)
  assert.match(composable, /catch \{[\s\S]{0,180}\}\n\s*return region\.value/)
  assert.doesNotMatch(composable, /status: 'blocked'[\s\S]{0,40}catch/)
})

test('the viewer’s location is only ever asked of our own origin', () => {
  // No third-party geo service: the two probes are same-origin paths, so the
  // address never travels anywhere it was not already going.
  assert.doesNotMatch(composable, /https?:\/\//)
  assert.match(composable, /\$fetch<string>\('\/cdn-cgi\/trace'/)
  assert.match(composable, /api<RegionResponse>\('\/playback\/region\/'/)
})

test('concurrent callers share one lookup per browser session', () => {
  assert.match(composable, /if \(pending\) return pending/)
  assert.match(composable, /if \(region\.value\.status !== 'unknown'\) return region\.value/)
})

test('the notice explains and dismisses instead of blocking playback', () => {
  assert.match(modal, /role="alertdialog"/)
  assert.match(modal, /@click="close"/)
  assert.match(modal, /onKeyStroke\('Escape'/)
  assert.match(modal, /باید|فقط با آی‌پی ایران/)
  // It never touches the player: closing it is the only thing it does to the page.
  assert.doesNotMatch(modal, /playerSource|applySource|pause\(\)/)
})

test('the watch page opens the notice on arrival and again when mirrors run out', () => {
  assert.match(watchPage, /void resolveRegion\(\)/)
  assert.match(watchPage, /<RegionPlaybackModal[\s\S]{0,160}@close="closeRegionNotice"/)
  // Re-shown at the one point mirror cycling has genuinely given up — after the
  // last mirror is retired and before the gateway last resort — and not on
  // every individual source failure along the way.
  assert.match(
    watchPage,
    /Every mirror is spent[\s\S]{0,300}revealRegionNotice\(\)[\s\S]{0,900}failedFamily === 'hevc'/,
  )
  assert.equal(watchPage.match(/(?<!function )revealRegionNotice\(\)/g).length, 1)
})

test('a trailer never raises the notice', () => {
  // Trailers come off our own media host, which answers everyone, so a viewer
  // abroad watching one has nothing to fix.
  assert.match(watchPage, /mode\.value !== 'trailer' && regionBlocked\.value/)
})

test('a dismissal lasts the tab, not the browser', () => {
  // sessionStorage, not localStorage: a viewer who switches their connection to
  // Iran should meet a clean page, not a decision they made before.
  assert.match(composable, /sessionStorage\.setItem\(DISMISS_KEY/)
  assert.doesNotMatch(composable, /localStorage/)
})
