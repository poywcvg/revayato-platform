import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const watchPage = readFileSync(
  new URL('../app/pages/watch/[slug].vue', import.meta.url),
  'utf8',
)
const watchParty = readFileSync(
  new URL('../app/pages/watch-party/[code].vue', import.meta.url),
  'utf8',
)
const subtitlePolicy = readFileSync(
  new URL('../app/utils/subtitlePolicy.ts', import.meta.url),
  'utf8',
)
const subtitleReadyNoticeText = subtitlePolicy.match(/hasCues \? '([^']+)'/)?.[1]

test('the subtitle hunt shows its progress in a status card, not the toast', () => {
  // The viewer must see that Persian subtitles are on the way so they keep
  // watching; the toast stays reserved for the one true "added" message.
  assert.doesNotMatch(watchPage, /softsubBanner/)
  assert.doesNotMatch(subtitlePolicy, /softsubBannerCopy|SoftsubBannerTone/)
  const hunt = watchPage.slice(watchPage.indexOf('async function runPlaybackSubtitleEnsure'))
  const huntBody = hunt.slice(0, hunt.indexOf('\n}\n'))
  assert.doesNotMatch(huntBody, /showPlayerNotice|dismissPlayerToast/)
  assert.match(huntBody, /setSubtitleHunt\('searching'\)/)
  assert.match(huntBody, /setSubtitleHunt\('preparing'\)/)
  assert.match(watchPage, /v-if="subtitleHunt"[\s\S]{0,200}role="status"[\s\S]{0,40}aria-live="polite"/)
  assert.match(watchPage, /@click="dismissSubtitleHunt"/)
  assert.match(watchPage, /function stopSoftsubHuntExhausted[\s\S]{0,160}setSubtitleHunt\('missing'\)/)
  assert.match(watchPage, /function applySoftsubWhenReady\(\) \{\s*clearSoftsubPoll\(\)\s*clearSubtitleHunt\(\)/)
})

test('out of fast rounds, one slow poll keeps the open player listening', () => {
  assert.match(watchPage, /softsubBackgroundPollStarted = true\s*setSubtitleHunt\('background'\)\s*startSoftsubPoll\(\{ maxAttempts: 30, intervalMs: 60_000 \}\)/)
  assert.match(watchPage, /softsubBackgroundPollStarted = false\s*subtitleHuntDismissed = false\s*clearSubtitleHunt\(\)/)
})

test('subtitle hunt status copy', async () => {
  const { subtitleHuntStatus } = await import('../app/utils/subtitlePolicy.ts')
  assert.equal(subtitleHuntStatus('searching').busy, true)
  assert.equal(subtitleHuntStatus('searching').durationMs, 0)
  assert.equal(subtitleHuntStatus('preparing').busy, true)
  assert.ok(subtitleHuntStatus('background').durationMs > 0)
  assert.match(subtitleHuntStatus('missing', true).title, /این قسمت/)
  assert.match(subtitleHuntStatus('missing').title, /این فیلم/)
})

test('the only subtitle message is a one-time, truthful "added" after cues land', () => {
  assert.equal(subtitleReadyNoticeText, 'زیرنویس فارسی اضافه شد')
  assert.match(watchPage, /if \(!softsubAnnounced\) \{\s*softsubAnnounced = true\s*showPlayerNotice\(subtitleReadyNotice\(true\)/)
  assert.match(watchPage, /softsubExhausted = false\s*softsubAnnounced = false/)
  assert.match(watchParty, /showNotice\(subtitleReadyNotice\(true\)\)/)
})

test('late subtitle responses cannot leak into another episode or version', () => {
  assert.match(watchPage, /let softsubRequestEpoch = 0/)
  assert.match(watchPage, /if \(requestEpoch !== softsubRequestEpoch\) return false/)
  assert.match(watchPage, /const versionChanged = current\[1\] !== previous\?\.\[1\]/)
  assert.match(watchPage, /softsubRequestEpoch \+= 1[\s\S]{0,300}clearSoftsubPoll\(\)/)
  assert.match(watchPage, /requestPlaybackSubtitleEnsure\(\)/)
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
