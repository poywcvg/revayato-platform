<script setup lang="ts">
import type { CinematicIconName, Movie } from '~/types'
import { externalRatings } from '~/utils/mediaRatings'
import { getRatingSourceConfig } from '~/data/ratingSources'

const props = defineProps<{ item: Movie }>()

const episodeCount = computed(() => props.item.episodes?.length || 0)
const primaryExternal = computed(() => externalRatings(props.item.ratings || [])[0] || null)

const facts = computed(() => {
  const rows: Array<{ label: string; value: string; icon: CinematicIconName; accent?: boolean }> = []
  if (props.item.year) {
    rows.push({ label: 'سال انتشار', value: String(props.item.year), icon: 'calendar' })
  }
  if (props.item.country) {
    rows.push({ label: 'کشور', value: props.item.country, icon: 'globe' })
  }
  if (props.item.type === 'series') {
    rows.push({ label: 'فصل و قسمت', value: `${props.item.seasons_count || 1} فصل · ${episodeCount.value || '—'} قسمت`, icon: 'layers' })
  } else if (props.item.duration_minutes) {
    rows.push({ label: 'مدت', value: `${props.item.duration_minutes} دقیقه`, icon: 'clock' })
  }
  if (props.item.language) {
    rows.push({ label: 'زبان', value: props.item.language, icon: 'language' })
  }
  if (props.item.imdb_rank) {
    rows.push({
      label: 'رتبه IMDb Top 250',
      value: `#${props.item.imdb_rank}`,
      icon: 'star',
      accent: true,
    })
  }
  if (primaryExternal.value) {
    const config = getRatingSourceConfig(primaryExternal.value.source)
    const scale = primaryExternal.value.scale === 100 && config.suffix === '%'
      ? ''
      : ` از ${primaryExternal.value.scale}`
    rows.push({
      label: config.label,
      value: `${primaryExternal.value.displayValue}${scale}`,
      icon: 'star',
      accent: true,
    })
  }
  if (props.item.has_downloads) {
    const qualities = props.item.download_qualities || []
    rows.push({
      label: 'دانلود',
      value: qualities.length ? qualities.join(' · ') : 'آماده',
      icon: 'download',
      accent: true,
    })
  }
  return rows
})
</script>

<template>
  <dl class="hide-scrollbar flex snap-x gap-2 overflow-x-auto pb-1 sm:grid sm:grid-cols-3 sm:overflow-visible sm:pb-0 xl:grid-cols-5" aria-label="اطلاعات اصلی عنوان">
    <div
      v-for="fact in facts"
      :key="fact.label"
      class="min-w-36 shrink-0 snap-start rounded-2xl p-3 sm:min-w-0"
      style="background: rgb(255 255 255 / 5.5%); box-shadow: inset 0 0 0 1px rgb(255 255 255 / 10%)"
    >
      <dt class="flex items-center gap-1.5 text-[10px] font-bold" style="color: var(--text-muted, #7a8681)">
        <CinematicIcon
          :name="fact.icon"
          class="size-3.5"
          :style="{ color: fact.accent ? 'var(--accent-rating, #f5c542)' : 'var(--media-accent, var(--theme-accent-primary))' }"
          :filled="fact.accent"
        />
        {{ fact.label }}
      </dt>
      <dd
        class="mt-1.5 truncate text-xs font-black sm:text-sm"
        :class="fact.accent && 'tabular-nums'"
        :style="{ color: fact.accent ? 'var(--accent-rating, #f5c542)' : 'var(--text-primary, #e6ebe9)' }"
      >
        {{ fact.value }}
      </dd>
    </div>
  </dl>
</template>
