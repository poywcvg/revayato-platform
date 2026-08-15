/**
 * Shared debounced-filter + URL-query-sync helper for admin list pages.
 *
 * Mirrors the reference pattern in `pages/admin/movies/index.vue`:
 * - 400ms debounce while `q` is being typed, 80ms otherwise.
 * - Filter state round-trips through `route.query` so back/forward preserves it.
 *
 * Usage:
 *   const { filters, page, debouncedWatch, syncQuery, clearFilters } = useDebouncedFilters(initial)
 *   debouncedWatch(() => { syncQuery(); load() })   // watch filters, reset page
 *   watch(page, () => { syncQuery(); load() })
 */
import type { WatchSource } from 'vue'
import { pageFromQuery } from './usePagination'

export interface UseDebouncedFiltersOptions<T> {
  /** Query stanza serialised to URL — keys present keep their value in the URL. */
  urlKeys: (keyof T & string)[]
  /** Debounce delay when `q` is set (default 400ms). */
  queryDebounceMs?: number
  /** Debounce delay otherwise (default 80ms). */
  defaultDebounceMs?: number
}

export function useDebouncedFilters<T extends object>(
  initial: T,
  options: UseDebouncedFiltersOptions<T>,
) {
  const route = useRoute()
  const router = useRouter()
  const { urlKeys, queryDebounceMs = 400, defaultDebounceMs = 80 } = options

  const page = ref(pageFromQuery(route.query.page))
  const filters = reactive<T>({ ...initial })

  let timer: ReturnType<typeof setTimeout> | undefined

  /** Serialise the given object into URL query params; empty values are dropped. */
  function toQuery(given: Partial<T> = {}) {
    const query: Record<string, string> = {}
    for (const key of urlKeys) {
      const value = (given as Record<string, unknown>)[key]
      if (value === undefined || value === null || value === '') continue
      query[key] = String(value)
    }
    if (page.value > 1) query.page = String(page.value)
    return query
  }

  function syncQuery() {
    router.replace({ query: toQuery() })
  }

  function debouncedWatch(effect: () => void, extraDeps: WatchSource[] = []) {
    const qGetter = () => String((filters as unknown as Record<string, unknown>).q ?? '')
    watch([qGetter, ...extraDeps], () => {
      clearTimeout(timer)
      page.value = 1
      const delay = qGetter() ? queryDebounceMs : defaultDebounceMs
      timer = setTimeout(effect, delay)
    })
  }

  function clearFilters(defaults: Partial<T>) {
    Object.assign(filters, defaults)
  }

  function resetToQuery(query: Record<string, string | string[]>) {
    for (const key of urlKeys) {
      const raw = query[key as string]
      ;(filters as unknown as Record<string, unknown>)[key] = Array.isArray(raw) ? String(raw[0] || '') : String(raw || '')
    }
  }

  onBeforeUnmount(() => clearTimeout(timer))

  return { filters, page, debouncedWatch, syncQuery, clearFilters, resetToQuery, toQuery }
}