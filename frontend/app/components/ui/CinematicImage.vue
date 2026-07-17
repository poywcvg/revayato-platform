<script setup lang="ts">
type ImageRatio = 'poster' | 'backdrop' | 'tile' | 'square'

const props = withDefaults(defineProps<{
  src?: string | null
  alt: string
  ratio?: ImageRatio
  priority?: boolean
  sizes?: string
  imageClass?: string
  fallbackLabel?: string
}>(), {
  src: '',
  ratio: 'poster',
  priority: false,
  sizes: '',
  imageClass: '',
  fallbackLabel: 'تصویر در دسترس نیست',
})

const failed = ref(false)
const loaded = ref(false)

const ratioClass: Record<ImageRatio, string> = {
  poster: 'aspect-[2/3]',
  backdrop: 'aspect-video',
  tile: 'aspect-[3/2]',
  square: 'aspect-square',
}

const preset: Record<ImageRatio, string | undefined> = {
  poster: 'cinemaPoster',
  backdrop: 'cinemaBackdrop',
  tile: 'cinemaTile',
  square: undefined,
}

const defaultSizes: Record<ImageRatio, string> = {
  poster: '(max-width: 640px) 46vw, (max-width: 1024px) 30vw, 220px',
  backdrop: '(max-width: 1024px) 100vw, 1280px',
  tile: '(max-width: 768px) 92vw, 640px',
  square: '(max-width: 640px) 32vw, 180px',
}

const placeholder: Record<ImageRatio, [number, number, number, number]> = {
  poster: [24, 36, 35, 8],
  backdrop: [32, 18, 35, 8],
  tile: [30, 20, 35, 8],
  square: [24, 24, 35, 8],
}

watch(() => props.src, () => {
  failed.value = false
  loaded.value = false
})
</script>

<template>
  <div class="cinematic-media relative overflow-hidden" :class="ratioClass[ratio]">
    <div v-if="src && !failed && !loaded" class="cinematic-image-skeleton absolute inset-0" aria-hidden="true" />
    <NuxtImg
      v-if="src && !failed"
      :src="src"
      :alt="alt"
      :preset="preset[ratio]"
      :sizes="sizes || defaultSizes[ratio]"
      :placeholder="placeholder[ratio]"
      placeholder-class="scale-105 opacity-70 saturate-50"
      class="absolute inset-0 h-full w-full object-cover transition-[transform,opacity] duration-300"
      :class="[imageClass, loaded ? 'opacity-100' : 'opacity-90']"
      :loading="priority ? 'eager' : 'lazy'"
      :preload="priority ? { fetchPriority: 'high' } : false"
      :fetchpriority="priority ? 'high' : 'low'"
      decoding="async"
      @load="loaded = true"
      @error="failed = true"
    />
    <CinematicImageFallback v-else :label="fallbackLabel" :compact="ratio === 'square'" />
    <slot />
  </div>
</template>
