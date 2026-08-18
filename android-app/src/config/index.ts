/**
 * Single source of truth for app configuration.
 *
 * Values come from the ambient env (react-native-config-style .env when present)
 * with checked-in development defaults so `pnpm android` works immediately on an
 * emulator (10.0.2.2 = host loopback from Android emulator).
 *
 * NOTE: this module must stay react-native-free so the data layer (adapter /
 * url helpers) is unit-testable under plain node jest. Platform-dependent
 * values live in utils/platform.
 */
export const API_BASE_URL =
  process.env.API_BASE_URL?.replace(/\/$/, '') ??
  'http://10.0.2.2:8000/api';

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
  memoryTtlMs: 30 * 60 * 1000, // 30m in-memory
  railsTtlMs: 24 * 60 * 60 * 1000, // persist 24h
  railsRefreshAgeMs: 6 * 60 * 60 * 1000, // background refresh after 6h
  namespace: 'revayato:cache:v1',
};

export const HTTP_TIMEOUT_MS = {
  default: 10_000,
  rails: 8_000,
  detail: 12_000,
};
