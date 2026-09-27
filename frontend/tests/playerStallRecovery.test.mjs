import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const player = readFileSync(
  new URL('../app/components/content/VideoPlayer.vue', import.meta.url),
  'utf8',
)
const watchPage = readFileSync(
  new URL('../app/pages/watch/[slug].vue', import.meta.url),
  'utf8',
)

test('repeated waiting events do not postpone the active stall watchdog', () => {
  assert.match(player, /if \(stallRecoverTimer\) return/)
  assert.doesNotMatch(player, /if \(stallRecoverTimer\) clearTimeout\(stallRecoverTimer\)[\s\S]{0,160}beginLoading/)
})

test('stalled sources get bounded recovery and then switch mirrors', () => {
  assert.match(player, /MAX_STALL_RECOVERY_ATTEMPTS = 3/)
  assert.match(player, /stallRecoveryAttempts >= MAX_STALL_RECOVERY_ATTEMPTS/)
  assert.match(player, /emit\('sourceFailed',[\s\S]*MEDIA_ERR_NETWORK/)
  assert.match(player, /props\.src !== failedSrc/)
})

test('progressive recovery nudges once, reloads once and preserves position', () => {
  assert.match(player, /stallRecoveryAttempts === 1[\s\S]*current\.currentTime = Math\.max\(0, nowSeconds \+ 0\.01\)/)
  assert.match(player, /resumeAfterSourceSeconds = toFilm\(nowSeconds\)[\s\S]*current\.load\(\)/)
})

test('a source that never emits waiting or error has a startup deadline', () => {
  assert.match(player, /SOURCE_STARTUP_TIMEOUT_MS = 10_000/)
  assert.match(player, /armSourceStartupWatchdog\(token\)/)
  assert.match(player, /current\.readyState >= HTMLMediaElement\.HAVE_CURRENT_DATA/)
  assert.match(player, /این منبع شروع نشد؛ در حال امتحان لینک بعدی/)
  assert.match(player, /cancelSourceStartupWatchdog\(\)[\s\S]*function handlePlaying/)
})

test('network failure skips other qualities on the same dead CDN origin', () => {
  assert.match(watchPage, /Number\(payload\?\.code\) === 2/)
  assert.match(watchPage, /new URL\(link\.url\)\.host\.toLowerCase\(\) === failedHost/)
  assert.match(watchPage, /failedPlaybackSources\.add\(link\.url\)/)
})

test('progressive files bypass hls.js while manifests keep the HLS path', () => {
  assert.match(player, /if \(!isHlsSource\(props\.src\)\)[\s\S]*element\.src = props\.src[\s\S]*element\.load\(\)/)
  // Both MIME spellings: Safari answers to the Apple one, several Android
  // WebViews only to the generic one, and either means native HLS.
  assert.match(player, /element\.canPlayType\('application\/vnd\.apple\.mpegurl'\) \|\| element\.canPlayType\('application\/x-mpegurl'\)/)
  assert.match(player, /hls\.loadSource\(props\.src\)/)
})

// A source change is the one moment the player's two clocks disagree: the media
// it is leaving may have started partway into the film, and the media it is
// loading almost certainly starts somewhere else. Everything carried across it
// therefore has to be in film time.

test('a source change carries the playhead in film time, not the media clock', () => {
  // The reading is taken while the media and the window props still agree...
  assert.match(player, /lastFilmSeconds = toFilm\(element\.currentTime\)/)
  // ...and it, not the outgoing element's own clock, is what survives the switch.
  assert.match(player, /resumeAfterSourceSeconds == null && hasLoadedSource && lastFilmSeconds > 1/)
  assert.doesNotMatch(player, /resumeAfterSourceSeconds = previous\.currentTime/)
})

test('a resume point is translated to the incoming media exactly once', () => {
  assert.match(player, /const local = Math\.max\(mediaOrigin\.value, toMedia\(resumeAfterSourceSeconds\)\)/)
  // prepareResumeAt takes film seconds, so it must store them unconverted.
  assert.match(player, /function prepareResumeAt\(seconds: number\) \{[\s\S]{0,120}resumeAfterSourceSeconds = seconds/)
})

test('a measured media origin never outlives the media it was measured on', () => {
  // refreshMediaOrigin keeps its last answer when there is nothing to measure,
  // so loading a new source has to clear it or the old window's offset leaks in.
  assert.match(player, /nativeNetworkRetryDone = false[\s\S]{0,400}mediaOrigin\.value = 0/)
})
