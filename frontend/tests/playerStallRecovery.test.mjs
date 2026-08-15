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
  assert.match(player, /resumeAfterSourceSeconds = nowSeconds[\s\S]*current\.load\(\)/)
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
  assert.match(player, /if \(element\.canPlayType\('application\/vnd\.apple\.mpegurl'\)\)/)
  assert.match(player, /hls\.loadSource\(props\.src\)/)
})
