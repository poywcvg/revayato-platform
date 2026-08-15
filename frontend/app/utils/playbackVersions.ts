import type { DownloadLink, PlaybackTextTrack, PlaybackVersion, PlaybackVersionKind } from '~/types'
import { isPlayablePlaybackUrl, pickStreamFriendlyLink, streamNetworkProfile } from '~/utils/downloadMeta'

function linkBlob(link: DownloadLink) {
  return `${link.kind || ''} ${link.label || ''} ${link.subtitle_type || ''} ${link.url || ''}`.toLowerCase()
}

export function isDubLink(link: DownloadLink) {
  const blob = linkBlob(link)
  const kind = String(link.kind || '').toLowerCase()
  if (['dubbed', 'dub', 'persian_dub', 'farsi_dub'].includes(kind)) return true
  return /(dubbed|\bdub\b|دوبله|persian dub|farsi dub)/.test(blob)
}

/** Burned-in / HardSub — including Persian “زیرنویس چسبیده”. */
export function isHardsubLink(link: DownloadLink) {
  const url = String(link.url || '').toLowerCase()
  // Explicit Soft CDN folders win over provider «چسبیده» mis-tags.
  if (isSoftEncodePath(url)) return false
  const blob = linkBlob(link)
  const kind = String(link.kind || '').toLowerCase()
  const subtitleType = String(link.subtitle_type || '').toLowerCase()
  if (['hardsub', 'hard-sub', 'hard_sub'].includes(kind)) return true
  if (subtitleType.includes('hard')) return true
  return /(hardsub|hard-sub|hard_sub|هاردساب|زیرنویس\s*چسبیده|چسبیده)/.test(blob)
}

/** SoftSub track — toggleable in player. */
export function isSoftsubLink(link: DownloadLink) {
  const url = String(link.url || '').toLowerCase()
  // CDN Soft/ paths are SoftSub even when the provider label says «چسبیده».
  if (isSoftEncodePath(url)) return true
  const blob = linkBlob(link)
  const kind = String(link.kind || '').toLowerCase()
  const subtitleType = String(link.subtitle_type || '').toLowerCase()
  if (/(softsub|soft-sub|soft_sub|soft\s*sub|زیرنویس\s*نرم|سافت\s*ساب)/.test(blob)) return true
  // Bare Farsi.Sub only when not explicitly HardSub-tagged.
  if (
    !['hardsub', 'hard-sub', 'hard_sub'].includes(kind)
    && !subtitleType.includes('hard')
    && /(farsi[\s._-]*sub|fa[\s._-]*sub)/.test(blob)
  ) {
    return true
  }
  if (isHardsubLink(link)) return true
  if (['subtitle', 'sub', 'softsub', 'hardsub', 'hard-sub', 'hard_sub'].includes(kind)) return true
  if (subtitleType) return true
  if (/\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(url)) return true
  return false
}

/** True SoftSub video encodes (not burned-in HardSub). */
export function isToggleableSoftsubLink(link: DownloadLink) {
  if (isDubLink(link)) return false
  const url = String(link.url || '').toLowerCase()
  if (isSoftEncodePath(url)) return true
  if (/\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(url)) return true
  if (isHardsubLink(link)) return false
  const kind = String(link.kind || '').toLowerCase()
  const subtitleType = String(link.subtitle_type || '').toLowerCase()
  if (['softsub', 'soft-sub', 'soft_sub'].includes(kind) || subtitleType.includes('soft')) return true
  if (/(softsub|soft[\s._-]*sub)/i.test(linkBlob(link))) return true
  return false
}

/** Normalize stream URLs so VTT `source_url` still matches after tokens/query drift. */
export function normalizePlaybackUrl(url?: string | null) {
  const raw = String(url || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw, 'https://revayato.invalid')
    const host = parsed.host.toLowerCase()
    const path = parsed.pathname.replace(/\/+$/, '') || '/'
    return `${host}${path}`.toLowerCase()
  } catch {
    return raw.split(/[?#]/)[0].replace(/\/+$/, '').toLowerCase()
  }
}

/** Filename fingerprint — survives CDN host rotation between Soft encodes. */
export function playbackUrlBasename(url?: string | null) {
  const normalized = normalizePlaybackUrl(url)
  if (!normalized) return ''
  const path = normalized.includes('/') ? normalized.slice(normalized.indexOf('/')) : normalized
  const base = path.split('/').pop() || ''
  return base.toLowerCase()
}

/**
 * Soft-encode identity without quality/codec/hash noise.
 * Lets 720p Soft VTT pair with 1080p Soft of the same release family
 * even when CDN hosts or release hashes rotate.
 */
export function softsubEncodeFingerprint(url?: string | null) {
  let base = playbackUrlBasename(url)
  if (!base) return ''
  base = base
    .replace(/\.(mkv|mp4|m4v|webm|mov|avi)$/i, '')
    .replace(/\b(2160p|1080p|720p|480p|360p|4k|uhd)\b/gi, '')
    .replace(/\b(10bit|8bit|x264|x265|h264|h265|hevc|avc|hdr10\+?|hdr|dolby.?vision|dovi|\bdv\b)\b/gi, '')
    .replace(/\b(atmos|truehd|dts-?hd|dts|ddp?5\.1|ddp|aac|ac3|eac3|flac|6ch|8ch|2ch|5\.1|7\.1)\b/gi, '')
    .replace(/\b(web-?dl|bluray|blu-?ray|hdcam|cam[\._-]?rip|camrip|\bcam\b|hdrip|webrip|remux|internal|proper|repack|extended|remastered|unrated|directors?\.?cut)\b/gi, '')
    .replace(/\b(full[\._-]?hd|fullhd|poke|yify|yts|pahe|bmb|onlyflix|rarbg|psa|sparkle|fgt|ntb|amzn|nf|dsnp|atvp|hmax|film2media|f2m)\b/gi, '')
    // CDN / release digests: .73a0144a or -f92582ae
    .replace(/[._-][0-9a-f]{6,12}(?=$|[._-])/gi, '')
    .replace(/\b(softsub|soft[\._-]?sub|farsi[\._-]?sub|fa[\._-]?sub|hardsub|hard[\._-]?sub)\b/gi, 'softsub')
    .replace(/[._-]+/g, '.')
    .replace(/^\.+|\.+$/g, '')
  return base.toLowerCase()
}

/** Title+year core shared by Soft encodes of the same release family. */
export function softsubTitleCore(url?: string | null) {
  const fp = softsubEncodeFingerprint(url)
  if (!fp) return ''
  const cleaned = fp
    .replace(/\.?softsub\.?/g, '.')
    .replace(/[._-]+/g, '.')
    .replace(/^\.+|\.+$/g, '')
  // Prefer "name.year" so CAM/Poke leftovers never block pairing.
  const yearCore = cleaned.match(/^(.+?\.\d{4})(?:\.|$)/)
  return yearCore?.[1] || cleaned
}

function isSoftEncodePath(url?: string | null) {
  const raw = String(url || '').toLowerCase()
  // Film2Media Soft/ SoftSub folders.
  if (/\/soft\/|\/softsub\/|\/soft-sub\/|\/soft_sub\//i.test(raw)) return true
  // /SUB|RSUB|BluSUB|SUBBlu/ + Farsi.Sub are toggleable Soft encodes.
  if (/\/(?:r?sub|blusub|subblu|softblu|softsub)\//i.test(raw) && /(?:farsi[\._-]?sub|fa[\._-]?sub|softsub|soft[\._-]?sub)/i.test(raw)) {
    return true
  }
  // Explicit SoftSub / Soft.Sub release names only — bare Farsi.Sub is often HardSub.
  return /(?:^|[._/\-])(softsub|soft[\._-]?sub)(?:[._/\-?]|$)/i.test(raw)
}

function isSidecarProviderTrack(track: PlaybackTextTrack) {
  const provider = String(track.provider || '').toLowerCase()
  return provider === 'subtitlestar' || provider === 'subzone'
}

/**
 * Pair WebVTT with the SoftSub stream being played.
 * Prefer exact source_url match (best sync). Fall back to SoftSub-family tracks
 * that belong to the same encode set — never attach Soft cues onto Dub/HardSub.
 */
export function pairSubtitleTracksForSource(
  tracks: readonly PlaybackTextTrack[],
  sourceUrl: string,
  softLinks: readonly DownloadLink[] = [],
): PlaybackTextTrack[] {
  if (!tracks.length) return []
  const normalized = normalizePlaybackUrl(sourceUrl)
  const sourceBase = playbackUrlBasename(sourceUrl)
  const sourceFingerprint = softsubEncodeFingerprint(sourceUrl)
  const playingSoft = isSoftEncodePath(sourceUrl)
    || isToggleableSoftsubLink({ url: sourceUrl } as DownloadLink)
  const playingDub = isDubLink({ url: sourceUrl, label: sourceUrl } as DownloadLink)

  // Soft encode present → keep SubtitleStar/Soft cues off Persian dub (use Soft path).
  // Dub-only titles (no Soft encode) still need toggleable online cues.
  const hasTrueSoftEncode = softLinks.some(link => isToggleableSoftsubLink(link))
  const blockDubSidecar = playingDub && hasTrueSoftEncode

  if (normalized) {
    const exact = tracks.filter(track => normalizePlaybackUrl(track.source_url) === normalized)
    if (exact.length && !(blockDubSidecar && exact.every(isSidecarProviderTrack))) {
      return [...exact]
    }
  }
  if (sourceBase) {
    const byName = tracks.filter(track => playbackUrlBasename(track.source_url) === sourceBase)
    if (byName.length && !(blockDubSidecar && byName.every(isSidecarProviderTrack))) {
      return [...byName]
    }
  }
  if (sourceFingerprint && playingSoft) {
    const byFingerprint = tracks.filter((track) => {
      const fp = softsubEncodeFingerprint(track.source_url)
      return Boolean(fp) && (fp === sourceFingerprint || fp.includes(sourceFingerprint) || sourceFingerprint.includes(fp))
    })
    if (byFingerprint.length) return [...byFingerprint]
  }
  const sourceCore = softsubTitleCore(sourceUrl)
  if (sourceCore && playingSoft) {
    const byCore = tracks.filter((track) => {
      const core = softsubTitleCore(track.source_url)
      return Boolean(core) && (core === sourceCore || core.includes(sourceCore) || sourceCore.includes(core))
    })
    if (byCore.length) return [...byCore]
  }

  const softEncodeLinks = softLinks.filter(isToggleableSoftsubLink)
  const softUrls = new Set(
    softEncodeLinks.map(link => normalizePlaybackUrl(link.url)).filter(Boolean),
  )
  const softBases = new Set(
    softEncodeLinks.map(link => playbackUrlBasename(link.url)).filter(Boolean),
  )
  const softFingerprints = new Set(
    softEncodeLinks.map(link => softsubEncodeFingerprint(link.url)).filter(Boolean),
  )
  if (softUrls.size) {
    const family = tracks.filter((track) => {
      const trackSource = normalizePlaybackUrl(track.source_url)
      return trackSource && softUrls.has(trackSource)
    })
    if (family.length) return [...family]
  }
  if (softBases.size) {
    const familyByName = tracks.filter((track) => {
      const base = playbackUrlBasename(track.source_url)
      return base && softBases.has(base)
    })
    if (familyByName.length) return [...familyByName]
  }
  if (softFingerprints.size && playingSoft) {
    const familyByFp = tracks.filter((track) => {
      const fp = softsubEncodeFingerprint(track.source_url)
      return Boolean(fp) && softFingerprints.has(fp)
    })
    if (familyByFp.length) return [...familyByFp]
  }
  const softCores = new Set(
    softEncodeLinks.map(link => softsubTitleCore(link.url)).filter(Boolean),
  )
  if (softCores.size && playingSoft) {
    const familyByCore = tracks.filter((track) => {
      const core = softsubTitleCore(track.source_url)
      return Boolean(core) && softCores.has(core)
    })
    if (familyByCore.length) return [...familyByCore]
  }

  // Legacy extracts without source_url — only safe on Soft playback.
  const unbound = tracks.filter(track => !normalizePlaybackUrl(track.source_url))
  if (playingSoft && unbound.length === 1 && tracks.length === 1) return [...unbound]
  if (!normalized && unbound.length) return [...unbound]

  // Soft CDN host rotated but both sides are Soft encodes of this title/episode.
  // Still refuse to attach Soft VTT onto Dub/HardSub — that desyncs cue timing.
  if (playingSoft && tracks.length === 1 && isSoftEncodePath(tracks[0]?.source_url)) {
    return [...tracks]
  }
  // One Soft-extracted WebVTT for this title/episode after host/quality drift.
  if (playingSoft && tracks.length === 1) {
    return [...tracks]
  }
  if (playingSoft) {
    const softSourced = tracks.filter(track => isSoftEncodePath(track.source_url))
    if (softSourced.length === 1) return [...softSourced]
  }

  // SubtitleStar IMDb sidecars on Soft encodes, HardSub-only, or Dub-only titles.
  // Skip Dub overlay when a Soft encode exists (burned-in / Soft path is preferred).
  const playingHard = !playingSoft && isHardsubLink({ url: sourceUrl } as DownloadLink)
  if ((!playingDub || !hasTrueSoftEncode) && (!playingHard || !hasTrueSoftEncode)) {
    const sidecar = tracks.filter(isSidecarProviderTrack)
    if (sidecar.length) {
      return [...new Map(sidecar.map(track => [track.src, track])).values()]
    }
  }
  if (playingSoft) {
    const sidecar = tracks.filter(isSidecarProviderTrack)
    if (sidecar.length) {
      return [...new Map(sidecar.map(track => [track.src, track])).values()]
    }
  }
  return []
}

function pickBest(links: readonly DownloadLink[]): DownloadLink | null {
  return pickStreamFriendlyLink(links, streamNetworkProfile())
}

function isSidecarSubtitleFile(link: DownloadLink) {
  return /\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(String(link.url || ''))
}

/**
 * Build the simple viewer choices: دوبله / زیرنویس فارسی.
 * Softsub WebVTT is paired with softsub streams so timing stays correct.
 */
export function buildPlaybackVersions(
  links: readonly DownloadLink[],
  subtitleTracks: readonly PlaybackTextTrack[] = [],
  fallbackUrl = '',
): PlaybackVersion[] {
  // Drop known-dead Soft CDN mirrors first so Soft/Dub lanes never 410 the player.
  const live = links.filter(link => isPlayablePlaybackUrl(link.url))
  const usable = live.length ? live : links.filter(link => Boolean(link.url))
  const dubLinks = usable.filter(isDubLink)
  // Prefer real SoftSub encodes for toggleable Persian text.
  const softEncodeLinks = usable.filter(isToggleableSoftsubLink)
  const hardEncodeLinks = usable.filter(link => !isDubLink(link) && isHardsubLink(link) && !isToggleableSoftsubLink(link))
  // Legacy SoftSub bucket (includes hardsub folded as SoftSub policy) when no true soft exists.
  const softLinks = softEncodeLinks.length
    ? softEncodeLinks
    : usable.filter(link => !isDubLink(link) && isSoftsubLink(link))
  const otherLinks = usable.filter(link => !isDubLink(link) && !isSoftsubLink(link))
  const safeFallback = isPlayablePlaybackUrl(fallbackUrl) ? fallbackUrl : (live.length ? '' : fallbackUrl)

  const versions: PlaybackVersion[] = []

  const bestDub = pickBest(dubLinks)
  if (bestDub) {
    const pairedDubSubtitleTracks = pairSubtitleTracksForSource(
      subtitleTracks,
      bestDub.url,
      softLinks.length ? softLinks : usable,
    )
    versions.push({
      id: 'dub',
      kind: 'dub',
      label: 'دوبله فارسی',
      url: bestDub.url,
      quality: bestDub.quality,
      // Only attach when we can pair cues to this exact dub source.
      subtitleTracks: pairedDubSubtitleTracks,
    })
  }

  const softVideoLinks = softLinks.filter(link => !isSidecarSubtitleFile(link))
  const bestSoft = pickBest(softVideoLinks) || pickBest(softLinks)
  if (bestSoft) {
    const hasToggleableSoft = softEncodeLinks.length > 0
    const hasExtractedTracks = subtitleTracks.length > 0
    let playUrl = bestSoft.url
    let playQuality = bestSoft.quality
    let burnedOnly = false
    let synced: PlaybackTextTrack[] = []

    if (hasExtractedTracks) {
      // SoftSub encode + extracted WebVTT — toggleable synced cues.
      synced = pairSubtitleTracksForSource(
        subtitleTracks,
        playUrl,
        softEncodeLinks.length ? softEncodeLinks : softLinks,
      )
      // CDN host/quality drift must not hide an already-extracted SoftSub track.
      if (!synced.length) {
        const playIsHard = !isSoftEncodePath(playUrl) && hardEncodeLinks.some(link => link.url === playUrl)
        if (playIsHard && hasToggleableSoft) {
          // Soft encode exists elsewhere — keep HardSub as burned-in-only.
          burnedOnly = true
        } else {
          // HardSub-only (or unmarked) streams still need the sidecar WebVTT in the player.
          synced = [...subtitleTracks]
        }
      }
    } else if (hardEncodeLinks.length) {
      // Film2Media Soft encode without WebVTT yet: fall back to HardSub so Persian
      // text stays visible (burned-in) until SoftSub extraction finishes.
      const bestHard = pickBest(hardEncodeLinks.filter(link => !isSidecarSubtitleFile(link))) || pickBest(hardEncodeLinks)
      if (bestHard) {
        playUrl = bestHard.url
        playQuality = bestHard.quality
        burnedOnly = true
      }
    } else if (
      !hasToggleableSoft
      && hardEncodeLinks.some(link => link.url === bestSoft.url)
    ) {
      burnedOnly = true
    } else {
      // Provider-tagged HardSub with bare Farsi.Sub (no Soft/ folder) — treat as burned-in
      // so the online player still shows Persian text before WebVTT arrives.
      const kind = String(bestSoft.kind || '').toLowerCase()
      const subtitleType = String(bestSoft.subtitle_type || '').toLowerCase()
      if (['hardsub', 'hard-sub', 'hard_sub'].includes(kind) || subtitleType.includes('hard')) {
        burnedOnly = true
      }
    }

    versions.push({
      id: 'softsub',
      kind: 'softsub',
      label: 'زیرنویس فارسی',
      url: playUrl,
      quality: playQuality,
      subtitleTracks: synced,
      burnedInSubtitles: burnedOnly,
    })
  }

  if (!bestSoft && subtitleTracks.length) {
    const bestOther = pickBest(otherLinks)
    const trackSource = subtitleTracks
      .map(track => String(track.source_url || '').trim())
      .find(url => url && !isSidecarSubtitleFile({ url } as DownloadLink))
    const url = bestOther?.url
      || (isPlayablePlaybackUrl(trackSource) ? trackSource : '')
      || safeFallback
    if (url) {
      let synced = pairSubtitleTracksForSource(subtitleTracks, url, softLinks.length ? softLinks : usable)
      if (!synced.length) synced = [...subtitleTracks]
      versions.push({
        id: 'softsub',
        kind: 'softsub',
        label: 'زیرنویس فارسی',
        url,
        quality: bestOther?.quality,
        subtitleTracks: synced,
      })
    }
  }

  if (!versions.length) {
    const bestOther = pickBest(otherLinks) || pickBest(usable)
    const url = bestOther?.url || safeFallback
    if (url) {
      versions.push({
        id: 'original',
        kind: 'original',
        label: 'پخش',
        url,
        quality: bestOther?.quality,
        subtitleTracks: pairSubtitleTracksForSource(subtitleTracks, url, usable),
      })
    }
  }

  return versions
}

export function resolvePlaybackVersion(
  versions: readonly PlaybackVersion[],
  preferredUrl?: string,
  preferredKind?: string,
): PlaybackVersion | null {
  if (!versions.length) return null
  const url = isPlayablePlaybackUrl(preferredUrl) ? String(preferredUrl || '').trim() : ''
  const normalizedPreferred = normalizePlaybackUrl(url)
  if (url) {
    const byUrl = versions.find(version => (
      version.url === url || normalizePlaybackUrl(version.url) === normalizedPreferred
    ))
    if (byUrl) return byUrl
    // Quality switch inside a version: keep that version's SoftSub tracks.
    const byKind = preferredKind
      ? versions.find(version => version.kind === preferredKind || version.id === preferredKind)
      : null
    if (byKind) {
      return {
        ...byKind,
        url,
      }
    }
  }
  if (preferredKind) {
    const byKind = versions.find(version => version.kind === preferredKind || version.id === preferredKind)
    if (byKind) return byKind
  }
  return versions.find(version => version.kind === 'softsub')
    || versions.find(version => version.kind === 'dub')
    || versions[0]
    || null
}

export function linksForVersionKind(links: readonly DownloadLink[], kind: PlaybackVersionKind) {
  if (kind === 'dub') return links.filter(isDubLink)
  if (kind === 'softsub' || kind === 'hardsub') {
    const soft = links.filter(link => (
      !isDubLink(link)
      && isToggleableSoftsubLink(link)
      && !isSidecarSubtitleFile(link)
    ))
    if (soft.length) return soft
    return links.filter(link => (
      !isDubLink(link)
      && isSoftsubLink(link)
      && !isSidecarSubtitleFile(link)
    ))
  }
  return links.filter(link => !isDubLink(link) && !isSoftsubLink(link))
}

/** True when any link is a Persian dub encode. */
export function linksImplyDub(links: readonly DownloadLink[] = []) {
  return links.some(isDubLink)
}

/** True when any link is SoftSub or HardSub (toggleable or burned-in). */
export function linksImplySubtitle(links: readonly DownloadLink[] = []) {
  return links.some(link => isSoftsubLink(link) || isHardsubLink(link))
}
