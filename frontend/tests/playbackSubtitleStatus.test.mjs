import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const watchPage = readFileSync(
  new URL('../app/pages/watch/[slug].vue', import.meta.url),
  'utf8',
)

test('missing subtitle progress is announced above the online player', () => {
  assert.match(watchPage, /v-if="softsubBanner"/)
  assert.match(watchPage, /role="status"/)
  assert.match(watchPage, /aria-live="polite"/)
  assert.match(watchPage, /softsubBanner\.tone === 'finding' \|\| softsubBanner\.tone === 'retrying'/)
  assert.match(watchPage, /showSoftsubBanner\('ready', 6500\)/)
})

test('late subtitle responses cannot leak into another episode or version', () => {
  assert.match(watchPage, /let softsubRequestEpoch = 0/)
  assert.match(watchPage, /if \(requestEpoch !== softsubRequestEpoch\) return false/)
  assert.match(watchPage, /const versionChanged = current\[1\] !== previous\?\.\[1\]/)
  assert.match(watchPage, /softsubRequestEpoch \+= 1[\s\S]{0,300}clearSoftsubPoll\(\)/)
  assert.match(watchPage, /requestPlaybackSubtitleEnsure\(\{ showBanner: true \}\)/)
})

test('a Persian track inside the file skips the server hunt', () => {
  assert.match(watchPage, /@embedded-subtitles="handleEmbeddedSubtitles"/)
  assert.match(watchPage, /function requestPlaybackSubtitleEnsure[\s\S]{0,120}if \(embeddedPersianAvailable\) return/)
  assert.match(watchPage, /embeddedPersianAvailable = true[\s\S]{0,200}clearSoftsubPoll\(\)/)
})

test('an exhausted server verdict stops polling and retries', () => {
  assert.match(watchPage, /result\?\.status === 'exhausted'/)
  assert.match(watchPage, /function stopSoftsubHuntExhausted[\s\S]{0,120}clearSoftsubPoll\(\)[\s\S]{0,40}clearSoftsubRetry\(\)/)
})
