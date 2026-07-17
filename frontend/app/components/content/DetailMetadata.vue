<script setup lang="ts">
import type { CinematicIconName, Movie } from '~/types'

const props = defineProps<{ item: Movie }>()

const episodeCount = computed(() => props.item.episodes?.length || 0)
const facts = computed(() => [
  { label: 'سال انتشار', value: String(props.item.year), icon: 'calendar' },
  { label: 'کشور', value: props.item.country, icon: 'globe' },
  props.item.type === 'series'
    ? { label: 'فصل و قسمت', value: `${props.item.seasons_count || 1} فصل · ${episodeCount.value || '—'} قسمت`, icon: 'layers' }
    : { label: 'مدت', value: `${props.item.duration_minutes} دقیقه`, icon: 'clock' },
  { label: 'زبان', value: props.item.language, icon: 'language' },
  { label: 'امتیاز', value: `${props.item.rating.toFixed(1)} از ۱۰`, icon: 'star', accent: true },
] satisfies Array<{ label: string; value: string; icon: CinematicIconName; accent?: boolean }>)
</script>

<template>
  <dl class="hide-scrollbar flex snap-x gap-2 overflow-x-auto pb-1 sm:grid sm:grid-cols-3 sm:overflow-visible sm:pb-0 xl:grid-cols-5" aria-label="اطلاعات اصلی عنوان">
    <div v-for="fact in facts" :key="fact.label" class="min-w-36 shrink-0 snap-start rounded-2xl bg-white/[.055] p-3 ring-1 ring-white/10 sm:min-w-0">
      <dt class="flex items-center gap-1.5 text-[10px] font-bold text-slate-400">
        <CinematicIcon :name="fact.icon" class="size-3.5" :class="fact.accent ? 'text-primary-400' : 'text-energy-300'" :filled="fact.accent" />
        {{ fact.label }}
      </dt>
      <dd class="mt-1.5 truncate text-xs font-black text-white sm:text-sm" :class="fact.accent ? 'tabular-nums text-primary-300' : ''">{{ fact.value }}</dd>
    </div>
  </dl>
</template>
