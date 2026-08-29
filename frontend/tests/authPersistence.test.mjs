import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { accessTokenExpiresAt, accessTokenNeedsRefresh } from '../app/utils/jwtSession.ts'

const authCookies = readFileSync(
  new URL('../app/composables/useAuthCookies.ts', import.meta.url),
  'utf8',
)
const apiClient = readFileSync(
  new URL('../app/composables/useApi.ts', import.meta.url),
  'utf8',
)
const authStore = readFileSync(
  new URL('../app/stores/auth.ts', import.meta.url),
  'utf8',
)
const authPlugin = readFileSync(
  new URL('../app/plugins/auth.ts', import.meta.url),
  'utf8',
)
const accountsApi = readFileSync(
  new URL('../../backend/apps/accounts/api.py', import.meta.url),
  'utf8',
)

const now = Date.parse('2026-08-26T12:00:00.000Z')

function accessToken(expiresAtMs) {
  const payload = Buffer.from(JSON.stringify({ token_type: 'access', exp: Math.floor(expiresAtMs / 1000) }))
    .toString('base64url')
  return `header.${payload}.signature`
}

test('access token expiry is read from the JWT payload', () => {
  assert.equal(accessTokenExpiresAt(accessToken(now)), now)
  assert.equal(accessTokenExpiresAt('not-a-jwt'), null)
  assert.equal(accessTokenExpiresAt('header..signature'), null)
  assert.equal(accessTokenExpiresAt(null), null)
})

test('a missing or nearly expired access token is rotated before it is used', () => {
  assert.equal(accessTokenNeedsRefresh(null, now), true)
  assert.equal(accessTokenNeedsRefresh('', now), true)
  assert.equal(accessTokenNeedsRefresh(accessToken(now - 1000), now), true)
  assert.equal(accessTokenNeedsRefresh(accessToken(now + 30_000), now), true)
})

test('a healthy access token is left alone, and so is one we cannot read', () => {
  assert.equal(accessTokenNeedsRefresh(accessToken(now + 30 * 60_000), now), false)
  // Guessing "expired" for an unreadable token would refresh on every request.
  assert.equal(accessTokenNeedsRefresh('opaque-token', now), false)
})

test('session cookies persist for the browser maximum of 400 days', () => {
  assert.match(authCookies, /AUTH_SESSION_MAX_AGE_SECONDS\s*=\s*60 \* 60 \* 24 \* 400/)
  assert.match(authCookies, /maxAge:\s*AUTH_SESSION_MAX_AGE_SECONDS/)
  assert.match(authCookies, /sameSite:\s*'lax'/)
  assert.match(authCookies, /secure:\s*import\.meta\.env\.PROD/)
  // The access cookie must not expire before the session: a vanished token makes
  // shared public endpoints answer as anonymous, which reads as a logout.
  assert.doesNotMatch(authCookies, /maxAge:\s*60 \* 60\b/)
})

test('the refresh token is HttpOnly and never written by page scripts', () => {
  assert.match(authCookies, /useCookie<string \| null>\('refresh_token', \{ \.\.\.shared, httpOnly: true \}\)/)
  // Safari's ITP caps *script-written* cookies at seven days whatever Max-Age
  // they ask for, so anything carrying the 400-day window has to arrive as a
  // response header. A document.cookie write here would reintroduce the cap.
  assert.doesNotMatch(authCookies, /document\.cookie/)
  assert.doesNotMatch(apiClient, /document\.cookie/)
  assert.doesNotMatch(authStore, /document\.cookie/)
  // Only a server render may write it — the browser's copy belongs to the API.
  assert.match(authCookies, /if \(import\.meta\.server\) refreshToken\.value = null/)
})

test('the API issues both session cookies itself, with HttpOnly on the credential', () => {
  assert.match(accountsApi, /response\.set_cookie\(\s*REFRESH_COOKIE_NAME, refresh, httponly=True/)
  assert.match(accountsApi, /response\.set_cookie\(\s*SESSION_FLAG_COOKIE_NAME, '1', httponly=False/)
  assert.match(accountsApi, /'samesite': 'Lax'/)
  assert.match(accountsApi, /'secure': not settings\.DEBUG/)
  assert.match(accountsApi, /MAX_BROWSER_COOKIE_DAYS = 400/)
  // Login, registration and rotation must all refresh the browser's window.
  assert.match(accountsApi, /_attach_session_cookies\(Response\(payload\), payload\['refresh'\]\)/)
  assert.match(accountsApi, /_attach_session_cookies\(\s*Response\(payload, status=status\.HTTP_201_CREATED\)/)
  assert.match(accountsApi, /if rotated:\s*\n\s*_attach_session_cookies\(response, rotated\)/)
  // Logout is the only thing that retires the cookie, and it accepts the token
  // from the cookie because the page that triggered it cannot read one.
  assert.match(accountsApi, /request\.data\.get\('refresh'\) or request\.COOKIES\.get\(REFRESH_COOKIE_NAME\)/)
  assert.match(accountsApi, /_clear_session_cookies\(Response\(status=status\.HTTP_204_NO_CONTENT\)\)/)
})

test('a browser-owned session is never handed back to page scripts', () => {
  // Cookie-authorised callers get only an access token; the rotated refresh
  // stays in the Set-Cookie header. Body callers (the native app) keep both.
  assert.match(accountsApi, /if from_cookie:\s*\n\s*data\.pop\('refresh', None\)/)
  assert.match(apiClient, /body: import\.meta\.server \? \{ refresh: refreshToken\.value \} : undefined/)
  assert.match(apiClient, /credentials: 'include'/)
  assert.doesNotMatch(authStore, /refreshToken\.value = session\.refresh/)
})

test('the session flag, not the credential, answers "is anyone signed in"', () => {
  assert.match(authCookies, /function hasSession\(\)/)
  assert.match(authCookies, /if \(import\.meta\.server\) return Boolean\(refreshToken\.value \|\| sessionFlag\.value\)/)
  assert.match(authStore, /Boolean\(accessToken\.value \|\| hasSession\(\)\)/)
  assert.match(apiClient, /if \(!hasSession\(\)\) return/)
})

test('the tab rotates before the access token dies, on every return to use', () => {
  assert.match(authPlugin, /visibilitychange/)
  assert.match(authPlugin, /ensureFreshAccessToken\(\)/)
  assert.match(apiClient, /async function ensureFreshAccessToken\(\)/)
  assert.match(apiClient, /accessTokenNeedsRefresh\(token\)/)
  assert.match(apiClient, /await ensureFreshAccessToken\(\)/)
})

test('rotation stores the new access token and keeps sessions on transient failures', () => {
  assert.match(apiClient, /accessToken\.value\s*=\s*result\.access/)
  assert.match(apiClient, /RECOVERABLE_REFRESH_STATUSES\s*=\s*\[400, 401, 403\]/)
  assert.match(apiClient, /if \(!RECOVERABLE_REFRESH_STATUSES\.includes\(status\)\) \{[\s\S]*?throw error/)
  assert.doesNotMatch(apiClient, /catch\s*\{\s*clearAuthCookies\(\)/)
})

test('a lost rotation race retries instead of ending the session', () => {
  // The API labels the two reasons a token is refused so the client can tell a
  // race it can recover from apart from a session that is genuinely over.
  assert.match(accountsApi, /'refresh_token_rotated' if rotated else 'token_not_valid'/)
  assert.match(accountsApi, /if from_cookie and detail\.get\('code'\) != 'refresh_token_rotated':/)
  assert.match(apiClient, /refreshFailureCode\(error\) === 'refresh_token_rotated'/)
  // Only one clearAuthCookies() call may exist, and it must sit behind the
  // client-side proof that the refresh token really is dead.
  assert.equal(apiClient.match(/clearAuthCookies\(\)/g)?.length, 1)
  assert.match(apiClient, /if \(import\.meta\.server\) \{[\s\S]*?return null[\s\S]*?\}\s*\/\/ Refresh token truly invalid/)
})

test('only a proven-dead refresh token ends the session', () => {
  assert.match(authStore, /\[401, 403\]\.includes\(errorStatus\(error\)\) && !hasSession\(\)/)
  assert.match(authStore, /function endSession\(\)/)
})

test('a server render relays the token it rotated on to the browser', () => {
  assert.match(apiClient, /if \(result\.refresh\) refreshToken\.value = result\.refresh/)
  assert.match(apiClient, /sessionFlag\.value = '1'/)
  assert.match(apiClient, /session\.renderAccessToken = result\.access/)
})
