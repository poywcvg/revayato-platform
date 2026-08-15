<script setup lang="ts">
import type { Movie } from '~/types'

const props = defineProps<{
  item: Movie
  index: number
  active: boolean
}>()

const imageFailed = ref(false)

const emit = defineEmits<{
  select: [index: number]
}>()

watch(() => props.item.poster_url, () => {
  imageFailed.value = false
})
</script>

<template>
  <button
    type="button"
    class="hero-movie-thumb"
    :class="active && 'hero-movie-thumb--active'"
    :aria-label="`نمایش اسلاید ${index + 1}: ${item.title}`"
    :aria-pressed="active"
    :aria-current="active ? 'true' : undefined"
    :data-hero-thumb="index"
    @click="emit('select', index)"
  >
    <span class="hero-movie-thumb__poster">
      <NuxtImg
        v-if="item.poster_url && !imageFailed"
        :src="item.poster_url"
        alt=""
        width="340"
        height="510"
        sizes="(max-width: 379px) 64px, (max-width: 767px) 76px, (max-width: 1023px) 104px, (max-width: 1279px) 128px, 160px"
        quality="86"
        class="hero-movie-thumb__image"
        loading="lazy"
        decoding="async"
        fetchpriority="low"
        draggable="false"
        @error="imageFailed = true"
      />
      <span v-else class="hero-movie-thumb__fallback" aria-hidden="true">
        <CinematicIcon name="image-off" />
      </span>
      <span v-if="active" class="hero-movie-thumb__selected" aria-hidden="true"><CinematicIcon name="play" filled /></span>
    </span>
  </button>
</template>

<style scoped>
.hero-movie-thumb {
  position: relative;
  z-index: 0;
  width: var(--hero-poster-width);
  margin-inline: 0;
  flex: none;
  border-radius: clamp(.55rem, 1vw, .9rem);
  opacity: 1;
  outline: none;
  scroll-snap-align: center;
  transform: translate3d(0, 0, 0) scale(.92);
  transform-origin: center bottom;
  -webkit-tap-highlight-color: transparent;
  transition: transform 420ms cubic-bezier(.16, 1, .3, 1);
}

.hero-movie-thumb:focus-visible {
  z-index: 2;
  transform: translate3d(0, 0, 0) scale(.97);
}

.hero-movie-thumb--active {
  z-index: 3;
  transform: translate3d(0, 0, 0) scale(1.04);
}

@media (min-width: 768px) {
  .hero-movie-thumb {
    margin-inline: 0;
    transform: translate3d(0, 0, 0) scale(.94);
  }

  .hero-movie-thumb--active {
    transform: translate3d(0, 0, 0) scale(1.06);
  }

  .hero-movie-thumb:focus-visible {
    transform: translate3d(0, 0, 0) scale(.98);
  }
}

.hero-movie-thumb__poster {
  position: relative;
  display: block;
  aspect-ratio: 2 / 3;
  overflow: hidden;
  border: 1px solid rgb(255 255 255 / 13%);
  border-radius: inherit;
  background: #121716;
  box-shadow: none;
  transition: border-color 320ms ease;
}

.hero-movie-thumb__image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: none;
  transition: transform 600ms cubic-bezier(.16, 1, .3, 1);
}

.hero-movie-thumb__fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at 50% 35%, rgb(176 228 204 / 10%), transparent 45%),
    linear-gradient(145deg, #151a18, #090c0b);
  color: rgb(176 228 204 / 58%);
}

.hero-movie-thumb__fallback :deep(svg) {
  width: clamp(1rem, 2.6vw, 1.35rem);
  height: clamp(1rem, 2.6vw, 1.35rem);
}

.hero-movie-thumb:focus-visible .hero-movie-thumb__poster { border-color: rgb(255 255 255 / 52%); }

.hero-movie-thumb:focus-visible .hero-movie-thumb__image { transform: translate3d(0, 0, 0) scale(1.06); }

.hero-movie-thumb--active .hero-movie-thumb__poster {
  border-color: #fff;
  box-shadow: none;
}

.hero-movie-thumb__selected {
  position: absolute;
  right: .4rem;
  bottom: .4rem;
  display: grid;
  width: clamp(1.3rem, 2.5vw, 1.8rem);
  aspect-ratio: 1;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 75%);
  border-radius: 50%;
  background: #050605;
  color: #fff;
}

.hero-movie-thumb__selected :deep(svg) { width: 34%; height: 34%; margin-left: .06rem; }

.hero-movie-thumb:focus-visible {
  outline: 3px solid rgb(var(--palette-sand-rgb) / 72%);
  outline-offset: 2px;
}

@media (hover: hover) and (pointer: fine) {
  .hero-movie-thumb:hover {
    z-index: 2;
    transform: translate3d(0, 0, 0) scale(.97);
  }

  .hero-movie-thumb:hover .hero-movie-thumb__poster {
    border-color: rgb(255 255 255 / 52%);
  }

  .hero-movie-thumb:hover .hero-movie-thumb__image {
    transform: translate3d(0, 0, 0) scale(1.06);
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-movie-thumb,
  .hero-movie-thumb__poster,
  .hero-movie-thumb__image { transition: none; }
}
</style>
