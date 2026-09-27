import type {
  CollectionItemMutation,
  CollectionPickRow,
  CollectionWritePayload,
  ContentType,
  PublicProfile,
  UserCollection,
} from '~/types'

/**
 * User collections ("کالکشن") + public-profile reads.
 *
 * `myCollections` is shared reactive state (Nuxt `useState`) so the profile
 * rail, the `/collections/my` grid, and the add-to-collection picker all stay
 * in sync after a create/rename/delete without re-fetching. Mutations are
 * optimistic where it is safe and reconcile against the server's authoritative
 * response (`item_count`, `added`/`removed`).
 */
export function useCollections() {
  const { api } = useApi()
  const authStore = useAuthStore()
  const route = useRoute()
  const myCollections = useState<UserCollection[]>('collections-mine', () => [])
  const loaded = useState('collections-mine-loaded', () => false)
  const pending = useState('collections-mine-pending', () => false)

  async function refreshMine(force = false) {
    if (!authStore.isAuthenticated) {
      myCollections.value = []
      loaded.value = true
      return
    }
    if (pending.value) return
    if (loaded.value && !force) return
    pending.value = true
    try {
      myCollections.value = await api<UserCollection[]>('/engagement/collections/')
      loaded.value = true
    } catch {
      // Keep the last known state if the API is momentarily unavailable.
    } finally {
      pending.value = false
    }
  }

  async function createCollection(payload: CollectionWritePayload) {
    const created = await api<UserCollection>('/engagement/collections/', {
      method: 'POST',
      body: payload,
    })
    myCollections.value = [created, ...myCollections.value.filter(c => c.slug !== created.slug)]
    return created
  }

  async function updateCollection(slug: string, payload: Partial<CollectionWritePayload>) {
    const updated = await api<UserCollection>(`/engagement/collections/${encodeURIComponent(slug)}/`, {
      method: 'PATCH',
      body: payload,
    })
    myCollections.value = myCollections.value.map(c => (c.id === updated.id ? { ...c, ...updated } : c))
    return updated
  }

  async function deleteCollection(slug: string) {
    await api(`/engagement/collections/${encodeURIComponent(slug)}/`, { method: 'DELETE' })
    myCollections.value = myCollections.value.filter(c => c.slug !== slug)
  }

  async function addItem(slug: string, contentType: ContentType, objectId: number, note = '') {
    const result = await api<CollectionItemMutation>(`/engagement/collections/${encodeURIComponent(slug)}/items/`, {
      method: 'POST',
      body: { content_type: contentType, object_id: objectId, note },
    })
    patchCount(slug, result.item_count)
    return result
  }

  async function removeItem(slug: string, contentType: ContentType, objectId: number) {
    const result = await api<CollectionItemMutation>(`/engagement/collections/${encodeURIComponent(slug)}/items/`, {
      method: 'DELETE',
      body: { content_type: contentType, object_id: objectId },
    })
    patchCount(slug, result.item_count)
    return result
  }

  function patchCount(slug: string, count: number) {
    myCollections.value = myCollections.value.map(c => (c.slug === slug ? { ...c, item_count: count } : c))
  }

  /** Which of my collections already contain this title (drives the picker). */
  async function containing(contentType: ContentType, objectId: number) {
    return api<CollectionPickRow[]>('/engagement/collections/containing/', {
      query: { content_type: contentType, object_id: objectId },
    })
  }

  /** PUBLIC collections built by any user that contain this title (discovery). */
  function fetchPublicContaining(contentType: ContentType, objectId: number) {
    return api<{ results: UserCollection[], count: number }>(
      '/engagement/collections/public-containing/',
      { query: { content_type: contentType, object_id: objectId } },
    )
  }

  // --- Read-only fetchers (use inside useAsyncData in pages) --- //
  function fetchMyCollection(slug: string) {
    return api<UserCollection>(`/engagement/collections/${encodeURIComponent(slug)}/`)
  }

  function fetchSharedCollection(token: string) {
    return api<UserCollection>(`/share/collection/${encodeURIComponent(token)}/`)
  }

  function fetchPublicCollection(username: string, slug: string) {
    return api<UserCollection>(
      `/users/${encodeURIComponent(username)}/collections/${encodeURIComponent(slug)}/`,
    )
  }

  function fetchPublicProfile(username: string) {
    return api<PublicProfile>(`/users/${encodeURIComponent(username)}/`)
  }

  if (import.meta.client && !loaded.value) {
    onNuxtReady(() => { void refreshMine() })
  }
  watch(() => authStore.isAuthenticated, () => {
    loaded.value = false
    void refreshMine(true)
  })

  return {
    myCollections,
    loaded: readonly(loaded),
    pending: readonly(pending),
    refreshMine,
    createCollection,
    updateCollection,
    deleteCollection,
    addItem,
    removeItem,
    containing,
    fetchPublicContaining,
    fetchMyCollection,
    fetchSharedCollection,
    fetchPublicCollection,
    fetchPublicProfile,
  }
}

/** Shared visibility labels/icons so every collection surface reads the same. */
export const COLLECTION_VISIBILITY = {
  public: { label: 'عمومی', icon: 'users', hint: 'روی پروفایلت دیده می‌شود و همه می‌توانند بازش کنند.' },
  unlisted: { label: 'با لینک', icon: 'share', hint: 'فهرست نمی‌شود؛ فقط با لینک اشتراک باز می‌شود.' },
  private: { label: 'خصوصی', icon: 'lock', hint: 'فقط خودت آن را می‌بینی.' },
} as const

/** Poster year off a collection item / review content, movie or series. */
export function contentYear(item: { release_year?: number | null; start_year?: number | null }) {
  return item.release_year ?? item.start_year ?? null
}

/** Detail-page path for a title, mirroring the movies/[slug] · series/[slug] routes. */
export function titlePath(contentType: ContentType, slug: string) {
  return `/${contentType === 'series' ? 'series' : 'movies'}/${slug}`
}
