<script setup lang="ts">
import type { Movie } from '~/types'
const props = withDefaults(defineProps<{ title: string; items: Movie[]; eyebrow?: string; href?: string; description?: string; dark?: boolean; showReasons?: boolean }>(), { eyebrow: '', href: '', description: '', dark: false, showReasons: false })

const rail = useTemplateRef<HTMLElement>('rail')
const currentIndex = ref(0)
const visibleCount = ref(1)
const hasOverflow = ref(false)
const dragging = ref(false)
let resizeObserver: ResizeObserver | undefined
let animationFrame = 0
let dragStartX = 0
let dragStartScroll = 0
let dragged = false
let suppressClick = false
let isRtl = false

const maxStartIndex = computed(() => Math.max(0, props.items.length - visibleCount.value))
const canGoPrevious = computed(() => hasOverflow.value && currentIndex.value > 0)
const canGoNext = computed(() => hasOverflow.value && currentIndex.value < maxStartIndex.value)
const totalPages = computed(() => Math.max(1, Math.ceil(props.items.length / visibleCount.value)))
const currentPage = computed(() => Math.min(totalPages.value - 1, Math.floor(currentIndex.value / visibleCount.value)))

function cards() {
  return rail.value ? [...rail.value.querySelectorAll<HTMLElement>('[data-carousel-card]')] : []
}

function updateCarouselState() {
  const element = rail.value
  const elements = cards()
  if (!element || !elements.length) {
    hasOverflow.value = false
    currentIndex.value = 0
    return
  }
  const railRect = element.getBoundingClientRect()
  const rects = elements.map(card => card.getBoundingClientRect())
  const visible = rects.filter((rect) => {
    const overlap = Math.min(rect.right, railRect.right) - Math.max(rect.left, railRect.left)
    return overlap >= rect.width * 0.6
  })
  visibleCount.value = Math.max(1, visible.length)
  hasOverflow.value = element.scrollWidth > element.clientWidth + 2

  let nearestIndex = 0
  let nearestDistance = Number.POSITIVE_INFINITY
  rects.forEach((rect, index) => {
    const distance = Math.abs(isRtl ? railRect.right - rect.right : rect.left - railRect.left)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearestIndex = index
    }
  })
  currentIndex.value = Math.min(nearestIndex, Math.max(0, props.items.length - visibleCount.value))
}

function scheduleStateUpdate() {
  cancelAnimationFrame(animationFrame)
  animationFrame = requestAnimationFrame(updateCarouselState)
}

function scrollToIndex(index: number, behavior: ScrollBehavior = 'smooth') {
  const targetIndex = Math.min(maxStartIndex.value, Math.max(0, index))
  cards()[targetIndex]?.scrollIntoView({ behavior, block: 'nearest', inline: 'start' })
  currentIndex.value = targetIndex
}

function goPrevious() {
  if (canGoPrevious.value) scrollToIndex(currentIndex.value - visibleCount.value)
}

function goNext() {
  if (canGoNext.value) scrollToIndex(currentIndex.value + visibleCount.value)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    goNext()
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    goPrevious()
  } else if (event.key === 'Home') {
    event.preventDefault()
    scrollToIndex(0)
  } else if (event.key === 'End') {
    event.preventDefault()
    scrollToIndex(maxStartIndex.value)
  }
}

function handlePointerDown(event: PointerEvent) {
  const element = rail.value
  if (!element || event.pointerType === 'touch' || event.button !== 0) return
  dragging.value = true
  dragged = false
  dragStartX = event.clientX
  dragStartScroll = element.scrollLeft
  element.setPointerCapture(event.pointerId)
}

function handlePointerMove(event: PointerEvent) {
  const element = rail.value
  if (!element || !dragging.value) return
  const distance = event.clientX - dragStartX
  if (Math.abs(distance) > 5) dragged = true
  if (!dragged) return
  event.preventDefault()
  element.scrollLeft = dragStartScroll + (isRtl ? distance : -distance)
}

function handlePointerEnd(event: PointerEvent) {
  const element = rail.value
  if (!element || !dragging.value) return
  dragging.value = false
  suppressClick = dragged
  if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId)
  scheduleStateUpdate()
  window.setTimeout(() => { suppressClick = false }, 0)
}

function handleClickCapture(event: MouseEvent) {
  if (!suppressClick) return
  event.preventDefault()
  event.stopPropagation()
}

onMounted(async () => {
  await nextTick()
  if (rail.value) isRtl = getComputedStyle(rail.value).direction === 'rtl'
  updateCarouselState()
  if (rail.value) {
    resizeObserver = new ResizeObserver(scheduleStateUpdate)
    resizeObserver.observe(rail.value)
  }
})

watch(() => props.items, async () => {
  await nextTick()
  scrollToIndex(0, 'auto')
  updateCarouselState()
}, { deep: false })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  cancelAnimationFrame(animationFrame)
})
</script>

<template>
  <section class="content-section render-later" :aria-label="title">
    <SectionHeader :title="title" :eyebrow="eyebrow" :href="href" :description="description" :dark="dark">
      <template #actions>
        <div v-if="hasOverflow" class="hidden items-center gap-1 sm:flex" aria-label="کنترل اسلایدر">
          <button type="button" class="carousel-control" :disabled="!canGoPrevious" :aria-label="`اسلاید قبلی ${title}`" @click="goPrevious"><CinematicIcon name="arrow-right" class="size-4.5" /></button>
          <button type="button" class="carousel-control" :disabled="!canGoNext" :aria-label="`اسلاید بعدی ${title}`" @click="goNext"><CinematicIcon name="arrow-left" class="size-4.5" /></button>
        </div>
      </template>
    </SectionHeader>
    <div v-if="items.length" class="relative">
      <div class="pointer-events-none absolute inset-y-0 right-0 z-20 w-12 bg-gradient-to-l from-canvas to-transparent transition-opacity sm:w-20" :class="canGoPrevious ? 'opacity-100' : 'opacity-0'" aria-hidden="true" />
      <div class="pointer-events-none absolute inset-y-0 left-0 z-20 w-12 bg-gradient-to-r from-canvas to-transparent transition-opacity sm:w-20" :class="canGoNext ? 'opacity-100' : 'opacity-0'" aria-hidden="true" />
      <div ref="rail" class="hide-scrollbar cinema-rail -mx-4 flex snap-x snap-mandatory gap-3.5 overflow-x-auto px-4 pb-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 sm:-mx-6 sm:gap-5 sm:px-6 lg:mx-0 lg:px-0" :class="dragging && 'is-dragging'" tabindex="0" role="region" aria-roledescription="carousel" :aria-label="title" @scroll.passive="scheduleStateUpdate" @keydown="handleKeydown" @pointerdown="handlePointerDown" @pointermove="handlePointerMove" @pointerup="handlePointerEnd" @pointercancel="handlePointerEnd" @click.capture="handleClickCapture" @dragstart.prevent>
        <MovieCard v-for="(item, index) in items" :key="item.id" data-carousel-card role="group" aria-roledescription="slide" :aria-label="`${index + 1} از ${items.length}: ${item.title}`" :item="item" :dark="dark" :reason="showReasons ? item.recommendation_reason : ''" class="w-[calc((100%-0.875rem)/2)] shrink-0 snap-start sm:w-[calc((100%-2.5rem)/3)] md:w-[calc((100%-3.75rem)/4)] lg:w-[calc((100%-3.75rem)/4)] xl:w-[calc((100%-5rem)/5)] 2xl:w-[calc((100%-6.25rem)/6)]" />
      </div>
      <div v-if="hasOverflow" class="mt-1 flex items-center justify-between gap-4 px-1">
        <span class="font-latin text-[10px] font-bold tabular-nums text-muted">{{ currentPage + 1 }} / {{ totalPages }}</span>
        <div class="flex max-w-44 flex-1 gap-1" aria-label="صفحه‌های اسلایدر">
          <button v-for="page in totalPages" :key="page" type="button" class="group flex min-h-6 flex-1 items-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :aria-label="`رفتن به صفحه ${page} از ${totalPages}`" :aria-current="page - 1 === currentPage ? 'true' : undefined" @click="scrollToIndex((page - 1) * visibleCount)"><span class="h-1.5 w-full rounded-full transition-colors" :class="page - 1 === currentPage ? 'bg-primary-500' : 'bg-line group-hover:bg-disabled'" /></button>
        </div>
      </div>
    </div>
    <EmptyState v-else />
  </section>
</template>
