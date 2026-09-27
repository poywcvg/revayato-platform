/**
 * Where the viewer is, as far as online playback is concerned.
 *
 * The video files this catalogue points at sit on Iranian CDNs that answer only
 * to Iranian addresses. From anywhere else the connection is dropped rather than
 * refused, so the player is never told anything: it waits on a `<video>` that
 * never starts until its own startup watchdog gives up with «این منبع در زمان
 * مناسب شروع نشد». The link is fine and the file is fine — the viewer is abroad,
 * and nothing else on the page is in a position to say so.
 *
 * Two first-party sources, in cost order. Cloudflare answers `/cdn-cgi/trace` at
 * the edge, so it costs no origin round-trip and reads the same geo database
 * that fills the `CF-IPCountry` header; `/api/playback/region/` reads that
 * header and covers anything not served through the edge. Neither sends the
 * viewer's address anywhere it was not already going.
 *
 * Unknown never blocks. A viewer whose country nothing resolved is far likelier
 * to be an Iranian behind something that strips the signal than someone abroad,
 * and telling a local viewer they are abroad is worse than saying nothing.
 */

/** Countries the playback CDNs serve. The API's own verdict wins when it answers. */
const PLAYBACK_REGIONS = ['IR']

/** Cloudflare's placeholders: no country for this address, and a Tor exit. */
const UNRESOLVED_COUNTRIES = new Set(['', 'XX', 'T1'])

const DISMISS_KEY = 'revayato:region-notice:v1'

export type ViewerRegionStatus = 'unknown' | 'allowed' | 'blocked'

export interface ViewerRegion {
  status: ViewerRegionStatus
  /** ISO-3166 alpha-2, or '' when nothing resolved one. */
  country: string
}

interface RegionResponse {
  country?: string
  known?: boolean
  allowed?: boolean
}

/** One browser, one lookup: concurrent callers share the round-trip. */
let pending: Promise<ViewerRegion> | null = null

function normalizeCountry(value: unknown) {
  const code = String(value || '').trim().toUpperCase().slice(0, 2)
  return UNRESOLVED_COUNTRIES.has(code) ? '' : code
}

/**
 * Whether this tab has already been told. Read at module scope so the state is
 * seeded with the stored answer instead of flashing the modal and withdrawing it.
 */
function storedDismissal() {
  if (!import.meta.client) return false
  try {
    return sessionStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    // Private mode or blocked storage: the notice simply shows again.
    return false
  }
}

/** `loc=FR` out of Cloudflare's `key=value` trace body. */
export function countryFromTrace(body: string) {
  return normalizeCountry(/^loc=([A-Za-z]{2})$/m.exec(String(body || ''))?.[1])
}

/** «فرانسه» for `FR`, from the browser's own tables; the code itself if it has none. */
export function persianCountryName(code: string) {
  if (!code) return ''
  try {
    return new Intl.DisplayNames(['fa'], { type: 'region' }).of(code) || code
  } catch {
    return code
  }
}

export function useViewerRegion() {
  const { api } = useApi()
  const region = useState<ViewerRegion>('viewer-region', () => ({ status: 'unknown', country: '' }))
  const dismissed = useState('viewer-region-dismissed', storedDismissal)

  function settle(country: string, allowed: boolean): ViewerRegion {
    region.value = { status: allowed ? 'allowed' : 'blocked', country }
    return region.value
  }

  /**
   * Answered by Cloudflare itself, so it never reaches our origin — and must
   * never be served from a cache, since the answer is about this viewer alone.
   */
  async function readEdgeTrace() {
    const body = await $fetch<string>('/cdn-cgi/trace', {
      responseType: 'text',
      retry: 0,
      timeout: 4_000,
      cache: 'no-store',
    })
    return countryFromTrace(String(body || ''))
  }

  async function readOriginRegion() {
    const answer = await api<RegionResponse>('/playback/region/', { timeout: 6_000 })
    return { country: normalizeCountry(answer?.country), allowed: answer?.allowed !== false }
  }

  /** Resolve once per browser session. Never throws: failure means unknown. */
  async function resolveRegion(): Promise<ViewerRegion> {
    if (!import.meta.client) return region.value
    if (region.value.status !== 'unknown') return region.value
    if (pending) return pending

    pending = (async () => {
      try {
        const country = await readEdgeTrace()
        if (country) return settle(country, PLAYBACK_REGIONS.includes(country))
      } catch {
        // No edge in front of us, or the probe was blocked. Ask the origin.
      }
      try {
        const answer = await readOriginRegion()
        if (answer.country) return settle(answer.country, answer.allowed)
      } catch {
        // Nothing resolved a country, so there is nothing to tell the viewer.
      }
      return region.value
    })().finally(() => {
      pending = null
    })

    return pending
  }

  /**
   * For this tab only. A viewer who switches their connection to Iran should
   * meet a clean page when they come back, not a decision they made before.
   */
  function dismissRegionNotice() {
    dismissed.value = true
    if (!import.meta.client) return
    try {
      sessionStorage.setItem(DISMISS_KEY, '1')
    } catch {
      // Nothing to persist to; the in-memory flag still holds for this page.
    }
  }

  const blocked = computed(() => region.value.status === 'blocked')
  const countryName = computed(() => persianCountryName(region.value.country))

  return {
    region,
    blocked,
    countryName,
    dismissed,
    dismissRegionNotice,
    resolveRegion,
  }
}
