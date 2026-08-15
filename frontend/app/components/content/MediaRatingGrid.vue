<script setup lang="ts">
import type { MediaRating } from '~/types/ratings'
import { externalRatings } from '~/utils/mediaRatings'

const props = withDefaults(defineProps<{
  ratings?: MediaRating[]
  loading?: boolean
  skeletonCount?: number
}>(), {
  ratings: () => [],
  loading: false,
  skeletonCount: 2,
})

const visible = computed(() => externalRatings(props.ratings || []))
</script>

<template>
  <div v-if="loading" class="rating-grid" aria-busy="true" aria-label="در حال بارگذاری امتیازها">
    <div v-for="index in skeletonCount" :key="index" class="rating-grid__skeleton" />
  </div>
  <div v-else-if="visible.length" class="rating-grid" aria-label="امتیاز منابع خارجی">
    <MediaRatingCard
      v-for="rating in visible"
      :key="`${rating.source}-${rating.criticType || 'default'}`"
      :rating="rating"
    />
  </div>
</template>

<style scoped>
.rating-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
  gap: 12px;
}

.rating-grid__skeleton {
  min-height: 4.25rem;
  border-radius: var(--radius-md, 12px);
  background: linear-gradient(
    90deg,
    var(--surface-2, var(--theme-bg-elevated)) 0%,
    var(--surface-3, var(--theme-bg-surface)) 50%,
    var(--surface-2, var(--theme-bg-elevated)) 100%
  );
  background-size: 200% 100%;
  animation: rating-shimmer 1.2s ease-in-out infinite;
}

@keyframes rating-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .rating-grid__skeleton {
    animation: none;
  }
}
</style>
