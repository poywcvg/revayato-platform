/**
 * Single source of truth for app configuration.
 *
 * The release APK is built with `API_BASE_URL` inlined at bundle time
 * (babel-plugin-transform-inline-environment-variables in babel.config.js), so
 * a shipped build always points at the production API. The dev fallback here
 * is `REVAYATO_DEFAULT_API_BASE`, which still prefers a real override and only
 * otherwise targets the production API — never a stale emulator address.
 *
 * NOTE: this module must stay react-native-free so the data layer (adapter /
 * url helpers) is unit-testable under plain node jest. Platform-dependent
 * values live in utils/platform.
 */
export const REVAYATO_DEFAULT_API_BASE =
  process.env.REVAYATO_DEFAULT_API_BASE?.replace(/\/$/, '') ??
  'https://revayato.com/api';

export const API_BASE_URL =
  process.env.API_BASE_URL?.replace(/\/$/, '') ?? REVAYATO_DEFAULT_API_BASE;

/**
 * Base URLs the app will try, in order, when a network/TLS failure occurs.
 * Primary is the public site. The direct-origin fallback reaches the VPS's
 * own public IP (plain HTTP, cleartext allowed for this exact origin) so the
 * app can load even on networks where the Cloudflare edge for revayato.com is
 * unreachable (e.g. some Iranian ISPs). The first base that responds is kept
 * for subsequent requests in this session.
 */
export const API_BASE_URL_FALLBACKS: string[] = [
  API_BASE_URL,
  ...(process.env.API_BASE_URL_FALLBACK
    ? process.env.API_BASE_URL_FALLBACK.split(',').map(s => s.trim().replace(/\/$/, ''))
    : ['http://45.13.119.115:8080/api']),
].filter(Boolean);

/**
 * Whether the app should force Persian RTL layout. Kept as a constant so the
 * RN I18nManager pin in index.js stays the single enforcement point.
 */
export const IS_RTL = true;

export const FONT_STACK = 'Vazirmatn';

/**
 * Cache / data-freshness settings (mirror the web app's SWR philosophy).
 * - rails/genres/countries persist to AsyncStorage for offline cold-start.
 * - browse pages stay memory-only (filters churn too fast).
 * - detail is session-scoped so back-nav and episode switching are instant.
 */
export const CACHE = {
  // Short in-memory TTL so web catalog changes reach the app within minutes.
  // Backend invalidates its Redis cache versions instantly on publish/change,
  // so the only stale window here is bounded by these client TTLs.
  memoryTtlMs: 5 * 60 * 1000, // 5m in-memory
  railsTtlMs: 12 * 60 * 60 * 1000, // persist 12h (offline cold-start window)
  railsRefreshAgeMs: 10 * 60 * 1000, // background refresh after 10m
  namespace: 'revayato:cache:v1',
};

export const HTTP_TIMEOUT_MS = {
  default: 10_000,
  rails: 8_000,
  detail: 12_000,
};
