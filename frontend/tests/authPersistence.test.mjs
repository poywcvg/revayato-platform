import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const authCookies = readFileSync(
  new URL('../app/composables/useAuthCookies.ts', import.meta.url),
  'utf8',
)
const apiClient = readFileSync(
  new URL('../app/composables/useApi.ts', import.meta.url),
  'utf8',
)

test('refresh cookie persists for the browser maximum of 400 days', () => {
  assert.match(authCookies, /AUTH_SESSION_MAX_AGE_SECONDS\s*=\s*60 \* 60 \* 24 \* 400/)
  assert.match(authCookies, /refreshToken[\s\S]*?maxAge:\s*AUTH_SESSION_MAX_AGE_SECONDS/)
  assert.match(authCookies, /sameSite:\s*'lax'/)
  assert.match(authCookies, /secure:\s*import\.meta\.env\.PROD/)
})

test('refresh rotation updates both tokens and keeps sessions on transient failures', () => {
  assert.match(apiClient, /accessToken\.value\s*=\s*result\.access/)
  assert.match(apiClient, /if \(result\.refresh\) refreshToken\.value\s*=\s*result\.refresh/)
  assert.match(apiClient, /status === 400 \|\| status === 401 \|\| status === 403/)
  assert.doesNotMatch(apiClient, /catch\s*\{\s*clearAuthCookies\(\)/)
})
