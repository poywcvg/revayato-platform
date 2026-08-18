/**
 * Lightweight URL-keyed cache + single-flight, no external query library.
 *
 * The API surface is a pure GET catalog, so a URL-keyed cache maps 1:1 to the
 * backend URIs (mirrors the web's "state + refresh from one place" philosophy).
 *
 * Layers:
 *  - memory Map (SWR) — instant back-nav, episode switching without refetching
 *  - single-flight Map — duplicate screen mounts share one in-flight promise
 *  - AsyncStorage — stable payloads (rails/genres/countries) survive cold start
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import {CACHE} from '../config';

interface CacheEntry<T> {
  data: T;
  savedAt: number;
}

const memoryCache = new Map<string, CacheEntry<unknown>>();
const inFlight = new Map<string, Promise<unknown>>();

export interface CachePolicy {
  /** Serve fresh memory cache without refetch while younger than this. */
  ttlMs?: number;
  /** Persist payload to AsyncStorage under `persistKey`. */
  persistKey?: string;
  /** Persist for offline/resume — payloads are stable. */
  persistTtlMs?: number;
}

export function cacheGet<T>(key: string, policy: CachePolicy = {}): T | null {
  const ttlMs = policy.ttlMs ?? CACHE.memoryTtlMs;
  const entry = memoryCache.get(key) as CacheEntry<T> | undefined;
  if (entry && Date.now() - entry.savedAt < ttlMs) {
    return entry.data;
  }
  return null;
}

export function memoryEntry<T>(key: string): CacheEntry<T> | null {
  return (memoryCache.get(key) as CacheEntry<T> | undefined) ?? null;
}

export function cachePut<T>(key: string, data: T, policy: CachePolicy = {}): void {
  memoryCache.set(key, {data, savedAt: Date.now()});
  if (policy.persistKey) {
    void AsyncStorage.setItem(
      persistKey(policy.persistKey),
      JSON.stringify({data, savedAt: Date.now()}),
    ).catch(() => undefined);
  }
}

/**
 * Fetch with dedupe + SWR + optional AsyncStorage hydration.
 * `persistPreview` (optional) lets callers render cached content while a fresh
 * fetch runs in the background.
 */
export async function fetchCached<T>(
  key: string,
  fetcher: () => Promise<T>,
  policy: CachePolicy = {},
): Promise<T> {
  // 1) single-flight across concurrent callers
  const pending = inFlight.get(key);
  if (pending) {return pending as Promise<T>;}

  // 2) fresh memory hit
  const hit = cacheGet<T>(key, policy);
  if (hit !== null) {return hit;}

  // 3) hydrate from AsyncStorage for stable payloads
  if (policy.persistKey) {
    const stored = await readPersist<T>(policy.persistKey, policy.persistTtlMs);
    if (stored !== null) {
      memoryCache.set(key, {data: stored, savedAt: Date.now() - (policy.ttlMs ?? 0)});
    }
  }

  const promise = (async () => {
    try {
      const data = await fetcher();
      memoryCache.set(key, {data, savedAt: Date.now()});
      if (policy.persistKey) {
        void AsyncStorage.setItem(
          persistKey(policy.persistKey),
          JSON.stringify({data, savedAt: Date.now()}),
        ).catch(() => undefined);
      }
      return data;
    } finally {
      inFlight.delete(key);
    }
  })();
  inFlight.set(key, promise);
  return promise;
}

export function clearCache(): void {
  memoryCache.clear();
  inFlight.clear();
}

function persistKey(key: string): string {
  return `${CACHE.namespace}:${key}`;
}

async function readPersist<T>(key: string, ttlMs?: number): Promise<T | null> {
  const raw = await AsyncStorage.getItem(persistKey(key)).catch(() => null);
  if (!raw) {return null;}
  try {
    const parsed = JSON.parse(raw) as {data: T; savedAt: number};
    if (ttlMs && Date.now() - parsed.savedAt > ttlMs) {return null;}
    return parsed.data;
  } catch {
    return null;
  }
}
