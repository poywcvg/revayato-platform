import type { ContentType, WatchlistItem } from '~/types'

interface LibraryEntry {
  content_type: ContentType
  object_id: number
}

function sameEntry(entry: LibraryEntry, contentType: ContentType, objectId: number) {
  return entry.content_type === contentType && entry.object_id === objectId
}

export function useLibrary() {
  const { api } = useApi()
  const authStore = useAuthStore()
  const route = useRoute()
  const watchlist = useState<LibraryEntry[]>('library-watchlist', () => [])
  const likes = useState<LibraryEntry[]>('library-likes', () => [])
  const loaded = useState('library-loaded', () => false)
  const pending = useState('library-pending', () => false)

  const watchlistIds = computed(() => watchlist.value.map(entry => entry.object_id))
  const likedIds = computed(() => likes.value.map(entry => entry.object_id))

  function isInWatchlist(id: number, contentType: ContentType = 'movie') {
    return watchlist.value.some(entry => sameEntry(entry, contentType, id))
  }

  function isLiked(id: number, contentType: ContentType = 'movie') {
    return likes.value.some(entry => sameEntry(entry, contentType, id))
  }

  async function refresh() {
    if (!authStore.isAuthenticated) {
      watchlist.value = []
      likes.value = []
      loaded.value = true
      return
    }
    if (pending.value) return
    pending.value = true
    try {
      const [watchlistItems, likeItems] = await Promise.all([
        api<WatchlistItem[]>('/engagement/watchlist/', { query: { list_type: 'watchlist' } }),
        api<LibraryEntry[]>('/engagement/likes/'),
      ])
      watchlist.value = watchlistItems.map(item => ({
        content_type: item.content_type,
        object_id: item.object_id,
      }))
      likes.value = likeItems.map(item => ({
        content_type: item.content_type,
        object_id: item.object_id,
      }))
      loaded.value = true
    } catch {
      // Keep the last known state if the API is temporarily unavailable.
    } finally {
      pending.value = false
    }
  }

  async function toggleWatchlist(id: number, contentType: ContentType = 'movie') {
    if (!authStore.isAuthenticated) {
      await navigateTo({ path: '/auth/login', query: { redirect: route.fullPath } })
      return false
    }
    const added = !isInWatchlist(id, contentType)
    watchlist.value = added
      ? [...watchlist.value, { content_type: contentType, object_id: id }]
      : watchlist.value.filter(entry => !sameEntry(entry, contentType, id))
    try {
      const response = await api<{ added: boolean }>('/engagement/watchlist/toggle/', {
        method: 'POST',
        body: { content_type: contentType, object_id: id, list_type: 'watchlist' },
      })
      if (response.added !== added) {
        watchlist.value = response.added
          ? [...watchlist.value.filter(entry => !sameEntry(entry, contentType, id)), { content_type: contentType, object_id: id }]
          : watchlist.value.filter(entry => !sameEntry(entry, contentType, id))
      }
      return response.added
    } catch {
      watchlist.value = added
        ? watchlist.value.filter(entry => !sameEntry(entry, contentType, id))
        : [...watchlist.value, { content_type: contentType, object_id: id }]
      throw new Error('watchlist_toggle_failed')
    }
  }

  async function toggleLike(id: number, contentType: ContentType = 'movie') {
    if (!authStore.isAuthenticated) {
      await navigateTo({ path: '/auth/login', query: { redirect: route.fullPath } })
      return false
    }
    const liked = !isLiked(id, contentType)
    likes.value = liked
      ? [...likes.value, { content_type: contentType, object_id: id }]
      : likes.value.filter(entry => !sameEntry(entry, contentType, id))
    try {
      const response = await api<{ liked: boolean }>('/engagement/likes/toggle/', {
        method: 'POST',
        body: { content_type: contentType, object_id: id },
      })
      if (response.liked !== liked) {
        likes.value = response.liked
          ? [...likes.value.filter(entry => !sameEntry(entry, contentType, id)), { content_type: contentType, object_id: id }]
          : likes.value.filter(entry => !sameEntry(entry, contentType, id))
      }
      return response.liked
    } catch {
      likes.value = liked
        ? likes.value.filter(entry => !sameEntry(entry, contentType, id))
        : [...likes.value, { content_type: contentType, object_id: id }]
      throw new Error('like_toggle_failed')
    }
  }

  if (import.meta.client && !loaded.value) {
    onNuxtReady(() => { void refresh() })
  }

  watch(() => authStore.isAuthenticated, () => { void refresh() })

  return {
    watchlist,
    likes,
    watchlistIds,
    likedIds,
    pending: readonly(pending),
    loaded: readonly(loaded),
    isInWatchlist,
    isLiked,
    toggleWatchlist,
    toggleLike,
    refresh,
  }
}
