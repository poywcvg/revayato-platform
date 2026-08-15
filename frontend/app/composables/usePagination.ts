export const CATALOG_PAGE_SIZE = 24
export const ACTORS_PAGE_SIZE = 36

export function pageFromQuery(value: unknown, fallback = 1) {
  const parsed = Number(Array.isArray(value) ? value[0] : value)
  if (!Number.isFinite(parsed) || parsed < 1) return fallback
  return Math.floor(parsed)
}

export function offsetFromPage(page: number, pageSize: number) {
  return Math.max(0, (Math.max(1, page) - 1) * pageSize)
}

export function totalPagesFor(count: number, pageSize: number) {
  if (count <= 0 || pageSize <= 0) return 1
  return Math.max(1, Math.ceil(count / pageSize))
}

export function clampPage(page: number, totalPages: number) {
  return Math.min(Math.max(1, page), Math.max(1, totalPages))
}

/** Build a compact page window for RTL pagination controls. */
export function paginationWindow(current: number, total: number, radius = 2) {
  if (total <= 1) return [1]
  const pages = new Set<number>([1, total, current])
  for (let index = current - radius; index <= current + radius; index += 1) {
    if (index >= 1 && index <= total) pages.add(index)
  }
  return [...pages].sort((left, right) => left - right)
}

export function useClientPagination<T>(items: Ref<T[]> | ComputedRef<T[]>, pageSize = CATALOG_PAGE_SIZE) {
  const route = useRoute()
  const router = useRouter()
  const page = computed(() => pageFromQuery(route.query.page))
  const total = computed(() => items.value.length)
  const totalPages = computed(() => totalPagesFor(total.value, pageSize))
  const safePage = computed(() => clampPage(page.value, totalPages.value))
  const offset = computed(() => offsetFromPage(safePage.value, pageSize))
  const pageItems = computed(() => items.value.slice(offset.value, offset.value + pageSize))

  async function goToPage(nextPage: number) {
    const target = clampPage(nextPage, totalPages.value)
    const query = { ...route.query } as Record<string, string | string[] | undefined>
    if (target <= 1) delete query.page
    else query.page = String(target)
    await router.replace({ query })
    if (import.meta.client) {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  watch(totalPages, (pages) => {
    if (page.value > pages) void goToPage(pages)
  })

  return {
    page: safePage,
    pageSize,
    total,
    totalPages,
    pageItems,
    goToPage,
  }
}
