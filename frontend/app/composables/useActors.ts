import type { Movie, SiteActor } from '~/types'
import { adaptApiCatalogItem, unwrapApiList, type ApiCatalogItem, type ApiListResponse } from '~/data/catalogAdapter'
import { preferEnglishName } from '~/utils/displayNames'

interface ApiActor extends SiteActor {
  movies?: ApiCatalogItem[]
  series?: ApiCatalogItem[]
}

function resolveActorPhoto(photo: string | null | undefined, mediaBase: string) {
  if (!photo) return null
  if (/^(?:https?:)?\/\//.test(photo) || photo.startsWith('data:') || photo.startsWith('blob:')) return photo
  if (!/^https?:\/\//.test(mediaBase)) return photo.startsWith('/') ? photo : `/media/${photo}`
  try {
    return new URL(photo.replace(/^\/+/, ''), `${mediaBase.replace(/\/$/, '')}/`).toString()
  } catch {
    return photo
  }
}

function adaptActor(actor: ApiActor, mediaBase: string): SiteActor & ApiActor {
  const names = preferEnglishName(actor.original_name, actor.name)
  return {
    ...actor,
    name: names.primary || actor.name,
    secondary_name: names.secondary || undefined,
    photo: resolveActorPhoto(actor.photo, mediaBase),
  }
}

export function useActors() {
  const config = useRuntimeConfig()
  const { api } = useApi()
  const mediaBase = computed(() => String(config.public.mediaCdnBaseUrl))

  async function list(options: {
    limit?: number
    offset?: number
    featured?: boolean
    withMeta: true
  }): Promise<{ items: Array<SiteActor & ApiActor>; count: number }>
  async function list(options?: {
    limit?: number
    offset?: number
    featured?: boolean
    withMeta?: false
  }): Promise<Array<SiteActor & ApiActor>>
  async function list(options: {
    limit?: number
    offset?: number
    featured?: boolean
    withMeta?: boolean
  } = {}) {
    const response = await api<ApiListResponse<ApiActor> | ApiActor[]>('/actors/', {
      query: {
        limit: options.limit ?? 48,
        offset: options.offset ?? 0,
        featured: options.featured ? '1' : undefined,
      },
    })
    const items = unwrapApiList(response).map(actor => adaptActor(actor, mediaBase.value))
    if (!options.withMeta) return items
    return {
      items,
      count: Array.isArray(response) ? items.length : Number(response.count || items.length),
    }
  }

  async function detail(slug: string) {
    const actor = await api<ApiActor>(`/actors/${encodeURIComponent(slug)}/`)
    const movies = (actor.movies || []).map(item => adaptApiCatalogItem(item, 'movie', mediaBase.value))
    const series = (actor.series || []).map(item => adaptApiCatalogItem(item, 'series', mediaBase.value))
    return {
      actor: adaptActor(actor, mediaBase.value),
      filmography: [...movies, ...series] as Movie[],
    }
  }

  return { list, detail }
}
