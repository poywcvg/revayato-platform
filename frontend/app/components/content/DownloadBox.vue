<script setup lang="ts">
import type { DownloadLink } from '~/types'
import { episodeNumberOf, qualityRank, seasonNumberOf } from '~/utils/downloadMeta'
import { isDubLink, isSoftsubLink } from '~/utils/playbackVersions'

const props = withDefaults(defineProps<{
  links: DownloadLink[]
  slug?: string
  mode?: 'play' | 'download'
}>(), {
  slug: '',
  mode: 'download',
})

export interface DownloadPlayRequest {
  url: string
  kind: 'dub' | 'softsub' | 'original'
  seasonNumber: number | null
  episodeNumber: number | null
}

const emit = defineEmits<{
  play: [request: DownloadPlayRequest]
}>()

type LinkGroupId = 'dub' | 'softsub' | 'other'

interface EnrichedLink extends DownloadLink {
  _seasonNumber: number | null
  _episodeNumber: number
  _qualityKey: string
  _qualityLabel: string
  _bucketId: LinkGroupId
}

interface QualityGroup {
  id: string
  bucketId: LinkGroupId
  title: string
  hint: string
  icon: 'audio' | 'subtitle' | 'download'
  qualityLabel: string
  links: EnrichedLink[]
}

interface SeasonGroup {
  id: string
  seasonNumber: number | null
  title: string
  episodeCount: number
  qualities: QualityGroup[]
}

interface MovieGroup {
  id: string
  bucketId: LinkGroupId
  title: string
  hint: string
  icon: 'audio' | 'subtitle' | 'download'
  links: EnrichedLink[]
}

const defsByBucket: Record<LinkGroupId, { title: string; hint: string; icon: 'audio' | 'subtitle' | 'download' }> = {
  dub: { title: 'دوبله فارسی', hint: 'صدای فارسی — در پخش آنلاین زیرنویس هم قابل فعال‌سازی است', icon: 'audio' },
  softsub: { title: 'زیرنویس فارسی', hint: 'زیرنویس قابل خاموش/روشن در پلیر', icon: 'subtitle' },
  other: { title: 'سایر نسخه‌ها', hint: 'کیفیت‌های دیگر', icon: 'download' },
}

const bucketOrder: Record<LinkGroupId, number> = { dub: 0, softsub: 1, other: 2 }

function bucketFor(link: DownloadLink): LinkGroupId {
  if (isDubLink(link)) return 'dub'
  if (isSoftsubLink(link)) return 'softsub'
  return 'other'
}

function qualityKeyOf(link: DownloadLink) {
  return String(link.quality || '').trim().toLowerCase() || 'default'
}

function qualityLabelOf(link: DownloadLink) {
  const cleaned = String(link.quality || '')
    .replace(/دوبله|زیرنویس|softsub|hardsub|فارسی/gi, '')
    .trim()
  if (cleaned) return cleaned
  const fromLabel = String(link.label || '').match(/(\d{3,4}\s*p|4k|uhd|fhd|hd)/i)?.[1]
  return fromLabel || 'کیفیت'
}

function seasonTitle(seasonNumber: number | null, sample?: DownloadLink) {
  if (typeof seasonNumber === 'number' && seasonNumber > 0) {
    return `فصل ${seasonNumber.toLocaleString('fa-IR')}`
  }
  const raw = String(sample?.season || '').trim()
  if (raw) return raw.startsWith('فصل') ? raw : `فصل ${raw}`
  return 'فصل'
}

function episodeLabel(link: EnrichedLink) {
  if (link._episodeNumber > 0) return `قسمت ${link._episodeNumber.toLocaleString('fa-IR')}`
  const ep = String(link.episode || '').trim()
  if (ep) return ep.startsWith('قسمت') ? ep : `قسمت ${ep}`
  return 'قسمت'
}

const enrichedLinks = computed<EnrichedLink[]>(() => {
  const seen = new Set<string>()
  const rows: EnrichedLink[] = []
  for (const link of props.links) {
    if (!link.url) continue
    const seasonNumber = seasonNumberOf(link)
    const episodeNumber = episodeNumberOf(link)
    const qualityKey = qualityKeyOf(link)
    const bucketId = bucketFor(link)
    const dedupe = `${seasonNumber ?? 'na'}|${episodeNumber}|${bucketId}|${qualityKey}|${link.url}`
    if (seen.has(dedupe)) continue
    seen.add(dedupe)
    rows.push({
      ...link,
      _seasonNumber: seasonNumber,
      _episodeNumber: episodeNumber,
      _qualityKey: qualityKey,
      _qualityLabel: qualityLabelOf(link),
      _bucketId: bucketId,
    })
  }
  return rows
})

const isSeriesDownload = computed(() => {
  return enrichedLinks.value.some(link => (
    link._seasonNumber != null
    || link._episodeNumber > 0
    || Boolean(link.season)
    || Boolean(link.episode)
    || /(?:فصل|قسمت|season|episode)\s*\d+/i.test(String(link.label || ''))
  ))
})

const boxTitle = computed(() => (
  props.mode === 'play' ? 'نسخه‌های پخش آنلاین' : 'لینک‌های دانلود'
))

const boxHint = computed(() => {
  const action = props.mode === 'play' ? 'پخش' : 'دانلود'
  return isSeriesDownload.value
    ? `فصل و کیفیت را باز کن، سپس قسمت را برای ${action} انتخاب کن`
    : `دوبله و زیرنویس جدا شده‌اند؛ کیفیت موردنظر را برای ${action} انتخاب کن`
})

const movieGroups = computed<MovieGroup[]>(() => {
  const buckets: Record<LinkGroupId, EnrichedLink[]> = { dub: [], softsub: [], other: [] }
  for (const link of enrichedLinks.value) buckets[link._bucketId].push(link)

  return (['dub', 'softsub', 'other'] as LinkGroupId[])
    .map((bucketId) => ({
      id: bucketId,
      bucketId,
      title: defsByBucket[bucketId].title,
      hint: defsByBucket[bucketId].hint,
      icon: defsByBucket[bucketId].icon,
      links: [...buckets[bucketId]].sort((a, b) => (
        qualityRank(b.quality) - qualityRank(a.quality)
        || String(a.label).localeCompare(String(b.label), 'fa')
      )),
    }))
    .filter(group => group.links.length)
})

const seasonGroups = computed<SeasonGroup[]>(() => {
  const seasons = new Map<string, {
    seasonNumber: number | null
    sample?: EnrichedLink
    qualities: Map<string, EnrichedLink[]>
  }>()

  for (const link of enrichedLinks.value) {
    const seasonKey = String(link._seasonNumber ?? 'na')
    let season = seasons.get(seasonKey)
    if (!season) {
      season = { seasonNumber: link._seasonNumber, sample: link, qualities: new Map() }
      seasons.set(seasonKey, season)
    }
    const qualityGroupKey = `${link._bucketId}|${link._qualityKey}`
    const list = season.qualities.get(qualityGroupKey)
    if (list) list.push(link)
    else season.qualities.set(qualityGroupKey, [link])
  }

  return [...seasons.values()]
    .sort((a, b) => (a.seasonNumber ?? 9999) - (b.seasonNumber ?? 9999))
    .map((season) => {
      const qualities = [...season.qualities.entries()]
        .map(([key, links]) => {
          const sample = links[0]!
          const sorted = [...links].sort((a, b) => (
            a._episodeNumber - b._episodeNumber
            || String(a.label).localeCompare(String(b.label), 'fa')
          ))
          return {
            id: `${season.seasonNumber ?? 'na'}|${key}`,
            bucketId: sample._bucketId,
            title: `${defsByBucket[sample._bucketId].title} · ${sample._qualityLabel}`,
            hint: defsByBucket[sample._bucketId].hint,
            icon: defsByBucket[sample._bucketId].icon,
            qualityLabel: sample._qualityLabel,
            links: sorted,
          } satisfies QualityGroup
        })
        .sort((a, b) => (
          bucketOrder[a.bucketId] - bucketOrder[b.bucketId]
          || qualityRank(b.qualityLabel) - qualityRank(a.qualityLabel)
          || a.qualityLabel.localeCompare(b.qualityLabel, 'fa')
        ))

      const episodeCount = new Set(
        qualities.flatMap(group => group.links.map(link => link._episodeNumber).filter(n => n > 0)),
      ).size

      return {
        id: `season-${season.seasonNumber ?? 'na'}`,
        seasonNumber: season.seasonNumber,
        title: seasonTitle(season.seasonNumber, season.sample),
        episodeCount,
        qualities,
      }
    })
    .filter(season => season.qualities.length)
})

const openSeasons = ref<Record<string, boolean>>({})
const openQualities = ref<Record<string, boolean>>({})
const openMovieGroups = ref<Record<string, boolean>>({})
const isDesktop = useMediaQuery('(min-width: 640px)')

watch(seasonGroups, (next) => {
  if (!isSeriesDownload.value) return
  const seasonState: Record<string, boolean> = { ...openSeasons.value }
  const qualityState: Record<string, boolean> = { ...openQualities.value }
  next.forEach((season) => {
    if (seasonState[season.id] === undefined) seasonState[season.id] = false
    season.qualities.forEach((quality) => {
      if (qualityState[quality.id] === undefined) qualityState[quality.id] = false
    })
  })
  openSeasons.value = seasonState
  openQualities.value = qualityState
}, { immediate: true })

watch(movieGroups, (next) => {
  if (isSeriesDownload.value) return
  const state: Record<string, boolean> = { ...openMovieGroups.value }
  next.forEach((group) => {
    if (state[group.id] === undefined) state[group.id] = false
  })
  openMovieGroups.value = state
}, { immediate: true })

watch(() => props.slug, (next, previous) => {
  if (next === previous) return
  openSeasons.value = {}
  openQualities.value = {}
  openMovieGroups.value = {}
})

function toggleSeason(id: string) {
  const next = !openSeasons.value[id]
  if (!isDesktop.value && next) {
    // Mobile accordion: one season open at a time.
    const closed: Record<string, boolean> = {}
    for (const season of seasonGroups.value) closed[season.id] = season.id === id
    openSeasons.value = closed
    return
  }
  openSeasons.value = { ...openSeasons.value, [id]: next }
}

function toggleQuality(id: string, seasonId: string) {
  const next = !openQualities.value[id]
  if (!isDesktop.value && next) {
    const season = seasonGroups.value.find(item => item.id === seasonId)
    const state: Record<string, boolean> = { ...openQualities.value }
    season?.qualities.forEach((quality) => {
      state[quality.id] = quality.id === id
    })
    openQualities.value = state
    return
  }
  openQualities.value = { ...openQualities.value, [id]: next }
}

function toggleMovieGroup(id: string) {
  const next = !openMovieGroups.value[id]
  if (!isDesktop.value && next) {
    const state: Record<string, boolean> = {}
    for (const group of movieGroups.value) state[group.id] = group.id === id
    openMovieGroups.value = state
    return
  }
  openMovieGroups.value = { ...openMovieGroups.value, [id]: next }
}

function fileName(link: EnrichedLink) {
  const quality = (link.quality || '').replace(/\s+/g, '')
  const base = props.slug || 'revayato'
  const extMatch = link.url.match(/\.(mp4|mkv|webm|avi|mov)(?:\?|$)/i)
  const ext = extMatch?.[1]?.toLowerCase() || 'mp4'
  const parts = [base]
  if (link._seasonNumber) parts.push(`s${link._seasonNumber}`)
  if (link._episodeNumber) parts.push(`e${link._episodeNumber}`)
  if (quality) parts.push(quality)
  return `${parts.join('-')}.${ext}`
}

function playRequest(link: EnrichedLink): DownloadPlayRequest {
  const kind: DownloadPlayRequest['kind'] = link._bucketId === 'dub'
    ? 'dub'
    : (link._bucketId === 'softsub' ? 'softsub' : 'original')
  return {
    url: link.url,
    kind,
    seasonNumber: link._seasonNumber,
    episodeNumber: link._episodeNumber > 0 ? link._episodeNumber : null,
  }
}
</script>

<template>
  <section
    v-if="movieGroups.length || seasonGroups.length"
    class="download-box"
    :data-mode="mode"
    :aria-labelledby="`media-access-box-title-${mode}`"
  >
    <header class="download-box__head">
      <div class="min-w-0">
        <h3 :id="`media-access-box-title-${mode}`" class="text-base font-black text-ink sm:text-lg">
          {{ boxTitle }}
        </h3>
        <p class="mt-0.5 text-[11px] leading-5 text-muted">
          {{ boxHint }}
        </p>
      </div>
      <span class="download-box__count">
        {{ enrichedLinks.length.toLocaleString('fa-IR') }}
      </span>
    </header>

    <!-- Movies -->
    <div v-if="!isSeriesDownload" class="download-box__groups">
      <section
        v-for="group in movieGroups"
        :key="group.id"
        class="download-box__group"
        :data-kind="group.bucketId"
      >
        <button
          type="button"
          class="download-box__group-toggle"
          :aria-expanded="Boolean(openMovieGroups[group.id])"
          :aria-controls="`${mode}-group-${group.id}`"
          @click="toggleMovieGroup(group.id)"
        >
          <span class="download-box__group-icon" aria-hidden="true">
            <CinematicIcon :name="group.icon" class="size-4" :stroke-width="1.6" />
          </span>
          <span class="min-w-0 flex-1 text-right">
            <span class="block text-sm font-black text-ink">{{ group.title }}</span>
            <span class="mt-0.5 block truncate text-[11px] text-muted">{{ group.hint }}</span>
          </span>
          <span class="download-box__group-meta">
            <span class="tabular-nums">{{ group.links.length.toLocaleString('fa-IR') }}</span>
            <CinematicIcon
              name="chevron-down"
              class="size-4 transition-transform"
              :class="openMovieGroups[group.id] && 'rotate-180'"
            />
          </span>
        </button>

        <ul
          v-show="openMovieGroups[group.id]"
          :id="`${mode}-group-${group.id}`"
          class="download-box__list"
        >
          <li
            v-for="(link, index) in group.links"
            :key="`${group.id}-${link.url}-${index}`"
            class="download-box__row"
          >
            <div class="min-w-0 flex flex-1 items-center gap-2.5">
              <span class="download-box__quality">{{ link._qualityLabel }}</span>
              <div class="min-w-0 hidden sm:block">
                <p class="truncate text-sm font-bold text-ink">{{ link.label || link._qualityLabel }}</p>
                <p v-if="link.size_label" class="mt-0.5 text-[10px] text-muted">حجم: {{ link.size_label }}</p>
              </div>
              <p v-if="link.size_label" class="truncate text-[10px] text-muted sm:hidden">حجم: {{ link.size_label }}</p>
            </div>
            <div class="flex shrink-0 items-center">
              <button
                v-if="mode === 'play'"
                type="button"
                class="download-box__action download-box__action--play"
                :aria-label="`پخش آنلاین ${link.label || link._qualityLabel}`"
                @click="emit('play', playRequest(link))"
              >
                <CinematicIcon name="play" class="size-3.5" filled />
                <span>پخش آنلاین</span>
              </button>
              <a
                v-else
                :href="link.url"
                class="download-box__action download-box__action--dl"
                :download="fileName(link)"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="دانلود"
              >
                <CinematicIcon name="download" class="size-3.5" />
                <span>دانلود</span>
              </a>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <!-- Series: season dropdown → quality dropdown → sorted episodes -->
    <div v-else class="download-box__seasons">
      <section
        v-for="season in seasonGroups"
        :key="season.id"
        class="download-box__season"
      >
        <button
          type="button"
          class="download-box__season-toggle"
          :aria-expanded="Boolean(openSeasons[season.id])"
          :aria-controls="`${mode}-season-${season.id}`"
          @click="toggleSeason(season.id)"
        >
          <span class="download-box__season-icon" aria-hidden="true">
            <CinematicIcon name="layers" class="size-4" :stroke-width="1.6" />
          </span>
          <span class="min-w-0 flex-1 text-right">
            <span class="block text-sm font-black text-ink">{{ season.title }}</span>
            <span class="mt-0.5 block truncate text-[11px] text-muted">
              {{ season.episodeCount.toLocaleString('fa-IR') }} قسمت ·
              {{ season.qualities.length.toLocaleString('fa-IR') }} کیفیت/نسخه
            </span>
          </span>
          <CinematicIcon
            name="chevron-down"
            class="size-5 shrink-0 text-muted transition-transform"
            :class="openSeasons[season.id] && 'rotate-180'"
          />
        </button>

        <div
          v-show="openSeasons[season.id]"
          :id="`${mode}-season-${season.id}`"
          class="download-box__groups download-box__groups--nested"
        >
          <section
            v-for="quality in season.qualities"
            :key="quality.id"
            class="download-box__group"
            :data-kind="quality.bucketId"
          >
            <button
              type="button"
              class="download-box__group-toggle"
              :aria-expanded="Boolean(openQualities[quality.id])"
              :aria-controls="`${mode}-quality-${quality.id}`"
              @click="toggleQuality(quality.id, season.id)"
            >
              <span class="download-box__group-icon" aria-hidden="true">
                <CinematicIcon :name="quality.icon" class="size-4" :stroke-width="1.6" />
              </span>
              <span class="min-w-0 flex-1 text-right">
                <span class="block text-sm font-black text-ink">{{ quality.title }}</span>
                <span class="mt-0.5 block truncate text-[11px] text-muted">
                  {{ quality.links.length.toLocaleString('fa-IR') }} قسمت · {{ quality.hint }}
                </span>
              </span>
              <span class="download-box__group-meta">
                <span class="tabular-nums">{{ quality.qualityLabel }}</span>
                <CinematicIcon
                  name="chevron-down"
                  class="size-4 transition-transform"
                  :class="openQualities[quality.id] && 'rotate-180'"
                />
              </span>
            </button>

            <ul
              v-show="openQualities[quality.id]"
              :id="`${mode}-quality-${quality.id}`"
              class="download-box__list download-box__list--episodes"
            >
              <li
                v-for="(link, index) in quality.links"
                :key="`${quality.id}-${link.url}-${index}`"
                class="download-box__row"
              >
                <div class="min-w-0 flex flex-1 items-center gap-2.5">
                  <span class="download-box__quality download-box__quality--episode">
                    {{ episodeLabel(link) }}
                  </span>
                  <div class="min-w-0 hidden sm:block">
                    <p class="truncate text-sm font-bold text-ink">
                      {{ episodeLabel(link) }}
                      <span class="text-muted"> · {{ quality.qualityLabel }}</span>
                    </p>
                    <p v-if="link.size_label" class="mt-0.5 text-[10px] text-muted">حجم: {{ link.size_label }}</p>
                  </div>
                  <p v-if="link.size_label" class="truncate text-[10px] text-muted sm:hidden">حجم: {{ link.size_label }}</p>
                </div>
                <div class="flex shrink-0 items-center">
                  <button
                    v-if="mode === 'play'"
                    type="button"
                    class="download-box__action download-box__action--play"
                    :aria-label="`پخش آنلاین ${episodeLabel(link)}`"
                    @click="emit('play', playRequest(link))"
                  >
                    <CinematicIcon name="play" class="size-3.5" filled />
                    <span>پخش آنلاین</span>
                  </button>
                  <a
                    v-else
                    :href="link.url"
                    class="download-box__action download-box__action--dl"
                    :download="fileName(link)"
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="دانلود"
                  >
                    <CinematicIcon name="download" class="size-3.5" />
                    <span>دانلود</span>
                  </a>
                </div>
              </li>
            </ul>
          </section>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.download-box {
  overflow: hidden;
  border-radius: 1.35rem;
  border: 1px solid color-mix(in srgb, var(--media-accent, #b0e4cc) 22%, var(--theme-border));
  background:
    linear-gradient(
      155deg,
      color-mix(in srgb, var(--media-accent, #b0e4cc) 12%, var(--theme-bg-surface)) 0%,
      color-mix(in srgb, #2dd4bf 8%, var(--theme-bg-surface)) 42%,
      color-mix(in srgb, var(--theme-bg-main) 62%, #07110e 38%) 100%
    );
}

.download-box[data-mode='download'] {
  border-color: color-mix(in srgb, #f5a524 28%, var(--theme-border));
  background:
    linear-gradient(
      155deg,
      color-mix(in srgb, #f5a524 10%, var(--theme-bg-surface)) 0%,
      color-mix(in srgb, #e8870b 7%, var(--theme-bg-surface)) 42%,
      color-mix(in srgb, var(--theme-bg-main) 64%, #120b04 36%) 100%
    );
}

.download-box__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  padding: 1rem 1.1rem .9rem;
  border-bottom: 1px solid color-mix(in srgb, var(--theme-border) 80%, transparent);
}

.download-box__count {
  display: inline-grid;
  place-items: center;
  min-width: 2rem;
  height: 2rem;
  padding-inline: .55rem;
  border-radius: .65rem;
  font-size: .7rem;
  font-weight: 900;
  color: #050807;
  background: color-mix(in srgb, var(--media-accent, #b0e4cc) 78%, white);
}

.download-box[data-mode='download'] .download-box__count {
  color: #2b1700;
  background: color-mix(in srgb, #f5a524 82%, white);
}

.download-box__groups {
  display: grid;
  gap: .45rem;
  padding: .55rem;
}

.download-box__seasons {
  display: grid;
  gap: .5rem;
  padding: .55rem;
}

.download-box__season {
  overflow: hidden;
  border-radius: 1.1rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 55%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--media-accent, #b0e4cc) 22%, var(--theme-border));
}

.download-box__season-toggle {
  display: flex;
  width: 100%;
  align-items: center;
  gap: .7rem;
  min-height: 3.4rem;
  padding: .75rem .85rem;
  text-align: right;
}

.download-box__season-icon {
  display: grid;
  width: 2.3rem;
  height: 2.3rem;
  flex: none;
  place-items: center;
  border-radius: .85rem;
  color: #050807;
  background: linear-gradient(140deg, color-mix(in srgb, var(--media-accent, #b0e4cc) 72%, white), color-mix(in srgb, #2dd4bf 55%, #ecfdf5));
}

.download-box__groups--nested {
  gap: .4rem;
  padding: 0 .55rem .6rem;
}

.download-box__group {
  overflow: hidden;
  border-radius: 1rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-border) 70%, transparent);
}

.download-box__group[data-kind='dub'] {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #7c5cff 28%, var(--theme-border));
}

.download-box__group[data-kind='softsub'],
.download-box__group[data-kind='hardsub'] {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #2dd4bf 26%, var(--theme-border));
}

.download-box__group-toggle {
  display: flex;
  width: 100%;
  align-items: center;
  gap: .7rem;
  min-height: 3.15rem;
  padding: .7rem .8rem;
  text-align: right;
}

.download-box__group-icon {
  display: grid;
  width: 2.15rem;
  height: 2.15rem;
  flex: none;
  place-items: center;
  border-radius: .8rem;
  color: #2e1065;
  background:
    radial-gradient(circle at 30% 25%, rgb(255 255 255 / 22%), transparent 55%),
    linear-gradient(140deg, color-mix(in srgb, #c4b5fd 64%, white), color-mix(in srgb, #7c5cff 50%, #ede9fe));
}

.download-box__group[data-kind='softsub'] .download-box__group-icon,
.download-box__group[data-kind='hardsub'] .download-box__group-icon {
  color: #0f766e;
  background: linear-gradient(140deg, color-mix(in srgb, #99f6e4 65%, white), color-mix(in srgb, #2dd4bf 44%, #f0fdfa));
}

.download-box__group[data-kind='dub'] .download-box__group-icon {
  color: #2e1065;
}

.download-box__group[data-kind='other'] .download-box__group-icon {
  color: #052e16;
  background: linear-gradient(140deg, color-mix(in srgb, var(--media-accent, #b0e4cc) 68%, white), color-mix(in srgb, #408a71 45%, #ecfdf5));
}

.download-box__group-meta {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: .35rem;
  color: var(--theme-text-muted);
  font-size: .7rem;
  font-weight: 800;
}

.download-box__list {
  display: grid;
  gap: .3rem;
  padding: 0 .45rem .5rem;
}

.download-box__list--episodes {
  max-height: min(58vh, 28rem);
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  scroll-padding-block: .35rem;
  padding-bottom: .65rem;
}

.download-box__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .55rem;
  min-height: 3.1rem;
  padding: .5rem .55rem;
  border-radius: .8rem;
  background: color-mix(in srgb, var(--theme-bg-surface) 70%, transparent);
}

.download-box__quality {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  height: 1.85rem;
  padding-inline: .4rem;
  border-radius: .5rem;
  font-size: .68rem;
  font-weight: 900;
  letter-spacing: .02em;
  color: #050807;
  background: linear-gradient(140deg, var(--media-accent, #b0e4cc), #2dd4bf);
}

.download-box__quality--episode {
  min-width: 4.1rem;
  flex: none;
  background: linear-gradient(140deg, #c4b5fd, #7c5cff);
  color: #1e1b4b;
}

.download-box__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .28rem;
  min-height: 2.75rem;
  min-width: 6.8rem;
  padding-inline: .7rem;
  border-radius: .7rem;
  font-size: .72rem;
  font-weight: 900;
  touch-action: manipulation;
}

.download-box__action--play {
  color: #04140f;
  background: linear-gradient(145deg, #5ef0c0 0%, #2dd4a8 55%, #1bb88f 100%);
  box-shadow: 0 8px 20px rgb(45 212 168 / 30%);
}

.download-box__action--dl {
  color: #1a0d00;
  background: linear-gradient(145deg, #ffc14d 0%, #f59e0b 52%, #e07800 100%);
  box-shadow: 0 8px 20px rgb(245 158 11 / 30%);
}

.download-box__action:focus-visible,
.download-box__season-toggle:focus-visible,
.download-box__group-toggle:focus-visible {
  outline: 2px solid var(--media-accent, #b0e4cc);
  outline-offset: -2px;
}

.download-box[data-mode='download'] .download-box__action:focus-visible,
.download-box[data-mode='download'] .download-box__season-toggle:focus-visible,
.download-box[data-mode='download'] .download-box__group-toggle:focus-visible {
  outline-color: #f5a524;
}

.download-box__season-toggle,
.download-box__group-toggle {
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}

@media (max-width: 639px) {
  .download-box {
    border-radius: 1.1rem;
  }

  .download-box__head {
    padding: .85rem .9rem .75rem;
  }

  .download-box__groups,
  .download-box__seasons {
    gap: .4rem;
    padding: .4rem;
  }

  .download-box__groups--nested {
    padding: 0 .4rem .5rem;
  }

  .download-box__season-toggle,
  .download-box__group-toggle {
    min-height: 3.35rem;
    padding: .7rem .75rem;
    gap: .55rem;
  }

  .download-box__season-icon,
  .download-box__group-icon {
    width: 2rem;
    height: 2rem;
    border-radius: .7rem;
  }

  .download-box__row {
    gap: .4rem;
    min-height: 3.1rem;
    padding: .4rem .45rem;
    flex-wrap: nowrap;
  }

  .download-box__action {
    min-height: 2.55rem;
    min-width: 0;
    padding-inline: .55rem;
    font-size: .68rem;
  }

  .download-box__action span {
    max-width: 4.5rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .download-box__list--episodes {
    max-height: min(52vh, 22rem);
  }
}

@media (min-width: 640px) {
  .download-box__row {
    min-height: 3.15rem;
    padding: .55rem .65rem;
  }

  .download-box__list--episodes {
    max-height: min(62vh, 34rem);
  }
}
</style>
