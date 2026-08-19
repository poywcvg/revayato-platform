/**
 * `useApiGet` — data hook with SWR semantics for list/detail screens.
 *
 * - renders immediately from a fresh memory/AsyncStorage hit (no flicker)
 * - single-flight dedupes duplicate in-flight requests
 * - background revalidation keeps the UI interactive and retains focus on TV
 */
import {useEffect, useRef, useState} from 'react';
import {AppState} from 'react-native';
import {CACHE} from '../config';
import {CachePolicy, fetchCached} from '../api/cache';

interface UseApiGetOptions<T, TResult = T> extends CachePolicy {
  /** Force refresh when app returns to foreground. */
  refreshOnResume?: boolean;
  select?: (data: T) => TResult;
}

interface UseApiGetState<TResult = unknown> {
  data: TResult | null;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useApiGet<T, TResult = T>(
  cacheKey: string,
  fetcher: () => Promise<T>,
  options: UseApiGetOptions<T, TResult> = {},
): UseApiGetState<TResult> {
  const ttlMs = options.ttlMs ?? CACHE.memoryTtlMs;
  const [data, setData] = useState<TResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const cacheKeyRef = useRef(cacheKey);
  cacheKeyRef.current = cacheKey;

  const load = async (initial = false) => {
    if (initial) {setIsLoading(true);}
    else {setIsRefreshing(true);}
    setError(null);
    try {
      const result = await fetchCached<T>(cacheKeyRef.current, fetcherRef.current, {
        ttlMs,
        persistKey: options.persistKey,
        persistTtlMs: options.persistTtlMs,
      });
      const next = (options.select ? options.select(result) : result) as TResult;
      setData(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'خطا در دریافت اطلاعات');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    void load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey]);

  useEffect(() => {
    if (!options.refreshOnResume) {return;}
    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') {void load(false);}
    });
    return () => sub.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {data, isLoading, isRefreshing, error, refetch: () => load(false)};
}
