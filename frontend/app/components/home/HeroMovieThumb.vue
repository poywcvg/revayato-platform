<script setup lang="ts">
import type { Movie } from '~/types'

defineProps<{
  item: Movie
  index: number
  active: boolean
}>()

const emit = defineEmits<{
  select: [index: number]
}>()
</script>

<template>
  <button
    type="button"
    class="hero-movie-thumb group"
    :class="active && 'hero-movie-thumb--active'"
    :aria-label="`نمایش اسلاید ${index + 1}: ${item.title}`"
    :aria-pressed="active"
    :aria-current="active ? 'true' : undefined"
    :data-hero-thumb="index"
    @click="emit('select', index)"
  >
    <span class="hero-movie-thumb__poster">
      <NuxtImg
        :src="item.poster_url"
        :alt="`پوستر ${item.title}`"
        width="144"
        height="216"
        sizes="72px sm:80px"
        quality="72"
        class="h-full w-full object-cover"
        loading="lazy"
        decoding="async"
        fetchpriority="low"
      />
      <span class="hero-movie-thumb__shade" aria-hidden="true" />
      <span v-if="active" class="hero-movie-thumb__selected"><CinematicIcon name="play" class="size-2.5" filled />فعال</span>
    </span>
    <span class="mt-1.5 block truncate px-0.5 text-[9px] font-bold" :class="active ? 'text-ink' : 'text-muted'" dir="rtl">{{ item.title }}</span>
  </button>
</template>

<style scoped>
.hero-movie-thumb {
  width: 4.5rem;
  flex: none;
  scroll-snap-align: center;
  color: var(--theme-text-secondary);
  opacity: .64;
  transform: translateY(0) scale(1);
  transition: opacity 180ms ease, transform 180ms ease;
}

.hero-movie-thumb:hover,
.hero-movie-thumb:focus-visible,
.hero-movie-thumb--active {
  opacity: 1;
}

.hero-movie-thumb:hover,
.hero-movie-thumb:focus-visible {
  transform: translateY(-2px);
}

.hero-movie-thumb--active {
  transform: translateY(-4px) scale(1.04);
}

.hero-movie-thumb__poster {
  position: relative;
  display: block;
  aspect-ratio: 2 / 3;
  overflow: hidden;
  border: 1px solid rgb(244 241 236 / 10%);
  border-radius: .75rem;
  background: var(--theme-bg-elevated);
  box-shadow: 0 8px 20px rgb(0 0 0 / 24%);
  transition: border-color 180ms ease, box-shadow 180ms ease;
}

.hero-movie-thumb:hover .hero-movie-thumb__poster,
.hero-movie-thumb:focus-visible .hero-movie-thumb__poster {
  border-color: rgb(196 106 45 / 52%);
}

.hero-movie-thumb--active .hero-movie-thumb__poster {
  border-color: var(--theme-accent-primary);
  box-shadow: 0 10px 26px rgb(0 0 0 / 34%), 0 0 0 2px rgb(196 106 45 / 22%), 0 0 24px rgb(196 106 45 / 20%);
}

.hero-movie-thumb__shade {
  position: absolute;
  inset: 0;
  background: rgb(6 6 7 / 28%);
  transition: opacity 180ms ease;
}

.hero-movie-thumb:hover .hero-movie-thumb__shade,
.hero-movie-thumb:focus-visible .hero-movie-thumb__shade,
.hero-movie-thumb--active .hero-movie-thumb__shade {
  opacity: 0;
}

.hero-movie-thumb__selected {
  position: absolute;
  right: .3rem;
  bottom: .3rem;
  display: inline-flex;
  align-items: center;
  gap: .2rem;
  border-radius: .35rem;
  background: var(--theme-accent-primary);
  padding: .18rem .3rem;
  color: var(--theme-bg-main);
  font-size: .5rem;
  font-weight: 900;
}

@media (min-width: 640px) {
  .hero-movie-thumb { width: 5rem; }
}

@media (prefers-reduced-motion: reduce) {
  .hero-movie-thumb,
  .hero-movie-thumb__poster,
  .hero-movie-thumb__shade { transition: none; }
}
</style>
