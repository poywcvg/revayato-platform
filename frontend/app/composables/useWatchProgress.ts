import type { ContentType, Movie } from '~/types'

export interface WatchProgressEntry {
  content_type: ContentType
  object_id: number
  slug: string
  title: string
  progress_percent: number
  updated_at: string
  episode_id?: number
}

const STORAGE_KEY = 'revayato:watch-progress:v1'
const MAX_ENTRIES = 40

function storageKeyFor(userId: number | string | null | undefined) {
  return userId ? `${STORAGE_KEY}:u${userId}` : `${STORAGE_KEY}:guest`
}

function clampProgress(value: number) {
  return Math.min(95, Math.max(0, Math.round(value)))
}

/**
 * Local continue-watching store. Progress is written while the user plays
 * content and merged onto catalog items so home/profile rails stay accurate.
 */
export function useWatchProgress() {
  const authStore = useAuthStore()
  const { catalog } = useCatalog()
  const entries = useState<WatchProgressEntry[]>('watch-progress-entries', () => [])
  const hydrated = useState('watch-progress-hydrated', () => false)

  const storageKey = computed(() => storageKeyFor(authStore.user?.id || null))

  function persist() {
    if (!import.meta.client) return
    try {
      localStorage.setItem(storageKey.value, JSON.stringify(entries.value.slice(0, MAX_ENTRIES)))
    } catch {
      /* private mode / quota */
    }
  }

  function hydrate() {
    if (!import.meta.client || hydrated.value) return
    hydrated.value = true
    try {
      const raw = localStorage.getItem(storageKey.value)
      const parsed = raw ? JSON.parse(raw) : []
      if (Array.isArray(parsed)) {
        entries.value = parsed
          .filter((item): item is WatchProgressEntry => Boolean(item?.slug && item?.object_id))
          .map(item => ({
            ...item,
            progress_percent: clampProgress(Number(item.progress_percent) || 0),
          }))
          .filter(item => item.progress_percent > 1 && item.progress_percent < 96)
      }
    } catch {
      entries.value = []
    }
    applyToCatalog()
  }

  function applyToCatalog() {
    if (!entries.value.length || !catalog.value.length) return
    const byKey = new Map(entries.value.map(entry => [`${entry.content_type}:${entry.object_id}`, entry]))
    let changed = false
    const next = catalog.value.map((item) => {
      const entry = byKey.get(`${item.type}:${item.id}`)
      if (!entry) return item
      if (item.progress_percent === entry.progress_percent) return item
      changed = true
      return { ...item, progress_percent: entry.progress_percent }
    })
    if (changed) {
      // useCatalog state is shared via useState — mutate through the same ref.
      const catalogState = useState<Movie[]>('catalog-items')
      catalogState.value = next
    }
  }

  function upsert(item: Pick<Movie, 'id' | 'slug' | 'title' | 'type' | 'duration_minutes'>, progressPercent: number, episodeId?: number) {
    const progress = clampProgress(progressPercent)
    if (progress <= 1) return
    try {
      useWatchTime().recordProgress(item, progress >= 96 ? 100 : progress)
    } catch { /* watch-time optional during early boot */ }
    const previous = entries.value.find(entry => entry.content_type === item.type && entry.object_id === item.id)
    if (progress >= 96) {
      remove(item.id, item.type)
      try {
        const { trackWatchProgress, personalizationEnabled } = useAnalyticsEvent()
        if (personalizationEnabled.value) trackWatchProgress(item, 100, 'complete')
      } catch { /* analytics optional during early boot */ }
      return
    }
    const next: WatchProgressEntry = {
      content_type: item.type,
      object_id: item.id,
      slug: item.slug,
      title: item.title,
      progress_percent: progress,
      updated_at: new Date().toISOString(),
      episode_id: episodeId,
    }
    entries.value = [
      next,
      ...entries.value.filter(entry => !(entry.content_type === item.type && entry.object_id === item.id)),
    ].slice(0, MAX_ENTRIES)
    persist()
    applyToCatalog()

    // Feed the recommendation profile without flooding: start once, then every ~10%.
    const previousProgress = previous?.progress_percent || 0
    const crossedBucket = Math.floor(progress / 10) > Math.floor(previousProgress / 10)
    if (!previous || crossedBucket) {
      try {
        const { trackWatchProgress, personalizationEnabled } = useAnalyticsEvent()
        if (personalizationEnabled.value) {
          trackWatchProgress(item, progress, previous ? 'progress' : 'start')
        }
      } catch { /* analytics optional during early boot */ }
    }
  }

  function remove(objectId: number, contentType: ContentType) {
    const before = entries.value.length
    entries.value = entries.value.filter(entry => !(entry.content_type === contentType && entry.object_id === objectId))
    if (entries.value.length !== before) {
      persist()
      applyToCatalog()
    }
  }

  function progressFor(objectId: number, contentType: ContentType = 'movie', episodeId?: number) {
    const entry = entries.value.find(item => item.content_type === contentType && item.object_id === objectId)
    if (!entry) return 0
    // A series entry belongs to one concrete episode. Never seek a newly selected
    // episode to the previous episode's timestamp.
    if (contentType === 'series' && episodeId && entry.episode_id !== episodeId) return 0
    return entry.progress_percent || 0
  }

  const continueWatching = computed(() => {
    const byKey = new Map(catalog.value.map(item => [`${item.type}:${item.id}`, item]))
    return entries.value
      .map((entry) => {
        const item = byKey.get(`${entry.content_type}:${entry.object_id}`)
        if (!item) return null
        return {
          ...item,
          progress_percent: entry.progress_percent,
        } as Movie
      })
      .filter((item): item is Movie => Boolean(item))
      .slice(0, 12)
  })

  watch(storageKey, () => {
    hydrated.value = false
    entries.value = []
    hydrate()
  })

  watch(() => catalog.value.length, () => {
    if (hydrated.value) applyToCatalog()
  })

  if (import.meta.client && !hydrated.value) {
    onNuxtReady(() => hydrate())
  }

  return {
    entries: readonly(entries),
    continueWatching,
    progressFor,
    upsert,
    remove,
    hydrate,
    applyToCatalog,
  }
}
