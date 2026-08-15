<script setup lang="ts">
import type { MediaRating } from '~/types/ratings'
import { formatScaleLabel } from '~/utils/mediaRatings'

const props = withDefaults(defineProps<{
  rating?: MediaRating | null
  /** @deprecated Prefer passing a MediaRating object. */
  value?: number
  compact?: boolean
  source?: 'imdb' | 'tmdb' | null
}>(), {
  rating: null,
  value: 0,
  compact: false,
  source: null,
})

const hasRating = computed(() => Boolean(props.rating) || (Number(props.value) > 0))
const scaleText = computed(() => (props.rating ? formatScaleLabel(props.rating) : '/ ۱۰'))
</script>

<template>
  <span
    v-if="hasRating"
    class="inline-flex items-center gap-1.5 rounded-lg bg-elevated/95 px-2 py-1 text-xs font-black text-ink shadow-sm ring-1 ring-line"
  >
    <template v-if="rating">
      <RatingSourceLogo :source="rating.source" />
      <span class="ltr-value tabular-nums" dir="ltr">
        {{ rating.displayValue }}
        <span v-if="!compact && scaleText" class="font-medium text-slate-400">{{ scaleText }}</span>
      </span>
    </template>
    <template v-else>
      <RatingSourceLogo v-if="source === 'imdb' || source === 'tmdb'" :source="source" />
      <CinematicIcon v-else name="star" class="size-4 text-primary-500" filled />
      <span class="ltr-value tabular-nums" dir="ltr">
        {{ Number(value).toFixed(1) }}
        <span v-if="!compact" class="font-medium text-slate-400">/ ۱۰</span>
      </span>
    </template>
  </span>
</template>
