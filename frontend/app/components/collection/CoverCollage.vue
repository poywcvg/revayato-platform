<script setup lang="ts">
const props = withDefaults(defineProps<{
  covers?: string[]
  accent?: string
  rounded?: string
}>(), {
  covers: () => [],
  accent: '#7c5cff',
  rounded: '1.25rem',
})

// Up to four posters drive the collage; fewer just tile what we have.
const tiles = computed(() => props.covers.slice(0, 4))
const gradient = computed(() => {
  const a = props.accent || '#7c5cff'
  return `linear-gradient(135deg, ${a}, color-mix(in srgb, ${a} 45%, #05201a))`
})
</script>

<template>
  <div class="collage" :style="{ borderRadius: rounded }">
    <div v-if="tiles.length" class="collage__grid" :data-count="tiles.length">
      <CinematicImage
        v-for="(cover, index) in tiles"
        :key="index"
        :src="cover"
        alt=""
        ratio="square"
        image-class="collage__img"
        class="collage__cell"
      />
    </div>
    <div v-else class="collage__empty" :style="{ background: gradient }" aria-hidden="true">
      <CinematicIcon name="layers" class="size-8 text-white/85" />
    </div>
    <span class="collage__wash" :style="{ background: gradient }" aria-hidden="true" />
    <slot />
  </div>
</template>

<style scoped>
.collage {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  width: 100%;
  height: 100%;
  background: color-mix(in srgb, var(--theme-bg-elevated) 88%, black);
}

.collage__grid {
  position: absolute;
  inset: 0;
  display: grid;
  gap: 2px;
}

.collage__grid[data-count='1'] { grid-template-columns: 1fr; }
.collage__grid[data-count='2'] { grid-template-columns: 1fr 1fr; }
.collage__grid[data-count='3'],
.collage__grid[data-count='4'] { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
.collage__grid[data-count='3'] .collage__cell:first-child { grid-row: span 2; }

.collage__cell { height: 100%; }
.collage :deep(.collage__img) { object-position: center 22%; }

.collage__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}

.collage__wash {
  position: absolute;
  inset: 0;
  z-index: 1;
  opacity: 0.32;
  mix-blend-mode: multiply;
  pointer-events: none;
}
</style>
