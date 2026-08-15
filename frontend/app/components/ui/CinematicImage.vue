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

const intrinsicSize: Record<ImageRatio, { width: number, height: number }> = {
  poster: { width: 600, height: 900 },
  backdrop: { width: 1600, height: 900 },
  tile: { width: 1200, height: 800 },
  square: { width: 600, height: 600 },
}

/** Catalog media is already webp on Caddy — skip IPX (avoids 1px SSR + fetch loops). */
const directSrc = computed(() => {
  const value = String(props.src || '').trim()
  if (!value) return ''
  try {
    if (value.startsWith('/media/')) return value
    const url = new URL(value, 'https://revayato.com')
    if (url.pathname.startsWith('/media/')) return `${url.pathname}${url.search}`
  } catch {
    /* keep original */
  }
  return ''
})

const useDirectMedia = computed(() => Boolean(directSrc.value))

watch(() => props.src, () => {
  failed.value = false
  loaded.value = false
})
</script>

<template>
  <div class="cinematic-media relative overflow-hidden" :class="ratioClass[ratio]">
    <div v-if="src && !failed && !loaded" class="cinematic-image-skeleton absolute inset-0" aria-hidden="true" />
    <img
      v-if="src && !failed && useDirectMedia"
      :src="directSrc"
      :alt="alt"
      :width="intrinsicSize[ratio].width"
      :height="intrinsicSize[ratio].height"
      :sizes="sizes || defaultSizes[ratio]"
      class="absolute inset-0 h-full w-full object-cover transition-[transform,opacity] duration-300"
      :class="[imageClass, loaded ? 'opacity-100' : 'opacity-90']"
      :loading="priority ? 'eager' : 'lazy'"
      :fetchpriority="priority ? 'high' : 'low'"
      decoding="async"
      @load="loaded = true"
      @error="failed = true"
    >
    <NuxtImg
      v-else-if="src && !failed"
      :src="src"
      :alt="alt"
      :preset="preset[ratio]"
      :sizes="sizes || defaultSizes[ratio]"
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
