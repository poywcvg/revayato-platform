<script setup lang="ts">
import type { CinematicIconName, Movie } from '~/types'
import { englishCatalogTitle } from '~/utils/displayNames'
const props = withDefaults(defineProps<{
  title: string
  items: Movie[]
  eyebrow?: string
  href?: string
  linkLabel?: string
  description?: string
  dark?: boolean
  showReasons?: boolean
  icon?: CinematicIconName | ''
}>(), {
  eyebrow: '',
  href: '',
  linkLabel: 'مشاهده همه',
  description: '',
  dark: false,
  showReasons: false,
  icon: '',
})

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
let activePointerId: number | null = null
const DRAG_THRESHOLD_PX = 10

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
  const element = rail.value
  const targetIndex = Math.min(maxStartIndex.value, Math.max(0, index))
  const card = cards()[targetIndex]
  if (!element || !card) return

  const reduced = import.meta.client
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const resolvedBehavior: ScrollBehavior = reduced ? 'auto' : behavior

  // Prefer native rail scroll — smoother and more consistent than scrollIntoView across RTL.
  const railRect = element.getBoundingClientRect()
  const cardRect = card.getBoundingClientRect()
  const delta = isRtl
    ? cardRect.right - railRect.right
    : cardRect.left - railRect.left
  element.scrollBy({ left: delta, behavior: resolvedBehavior })
  currentIndex.value = targetIndex
  scheduleStateUpdate()
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
  const target = event.target as HTMLElement | null
  // Let dedicated controls keep their own click handling.
  if (target?.closest('button, input, select, textarea, [role="button"]')) return

  activePointerId = event.pointerId
  dragging.value = false
  dragged = false
  dragStartX = event.clientX
  dragStartScroll = element.scrollLeft
}

function handlePointerMove(event: PointerEvent) {
  const element = rail.value
  if (!element || activePointerId !== event.pointerId) return

  const distance = event.clientX - dragStartX
  if (!dragged && Math.abs(distance) <= DRAG_THRESHOLD_PX) return

  if (!dragged) {
    dragged = true
    dragging.value = true
    // Capture only after a real drag so simple clicks still hit the card link.
    element.setPointerCapture(event.pointerId)
  }

  event.preventDefault()
  element.scrollLeft = dragStartScroll + (isRtl ? distance : -distance)
}

function handlePointerEnd(event: PointerEvent) {
  const element = rail.value
  if (!element || activePointerId !== event.pointerId) return

  const wasDragging = dragged
  activePointerId = null
  dragging.value = false
  suppressClick = wasDragging
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
    <SectionHeader :title="title" :eyebrow="eyebrow" :href="href" :link-label="linkLabel" :description="description" :dark="dark" :icon="icon">
      <template #actions>
        <div v-if="hasOverflow" class="hidden items-center gap-1 sm:flex" aria-label="کنترل اسلایدر">
          <button type="button" class="carousel-control" :disabled="!canGoPrevious" :aria-label="`اسلاید قبلی ${title}`" @click="goPrevious"><CinematicIcon name="arrow-right" class="size-4.5" /></button>
          <button type="button" class="carousel-control" :disabled="!canGoNext" :aria-label="`اسلاید بعدی ${title}`" @click="goNext"><CinematicIcon name="arrow-left" class="size-4.5" /></button>
        </div>
      </template>
    </SectionHeader>
    <div v-if="items.length" class="relative">
      <div class="pointer-events-none absolute inset-y-0 right-0 z-20 w-8 bg-gradient-to-l from-canvas to-transparent transition-opacity sm:w-20" :class="canGoPrevious ? 'opacity-100' : 'opacity-0'" aria-hidden="true" />
      <div class="pointer-events-none absolute inset-y-0 left-0 z-20 w-8 bg-gradient-to-r from-canvas to-transparent transition-opacity sm:w-20" :class="canGoNext ? 'opacity-100' : 'opacity-0'" aria-hidden="true" />
      <div ref="rail" class="hide-scrollbar cinema-rail rail-bleed flex snap-x snap-mandatory overflow-x-auto pb-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 sm:pb-5" :class="dragging && 'is-dragging'" tabindex="0" role="region" aria-roledescription="carousel" :aria-label="title" @scroll.passive="scheduleStateUpdate" @keydown="handleKeydown" @pointerdown="handlePointerDown" @pointermove="handlePointerMove" @pointerup="handlePointerEnd" @pointercancel="handlePointerEnd" @click.capture="handleClickCapture" @dragstart.prevent>
        <MovieCard v-for="(item, index) in items" :key="`${item.type}:${item.id}`" data-carousel-card role="group" aria-roledescription="slide" :aria-label="`${index + 1} از ${items.length}: ${englishCatalogTitle(item)}`" :item="item" :dark="dark" :reason="showReasons ? item.recommendation_reason : ''" class="cinema-rail-card" />
      </div>
      <div v-if="hasOverflow" class="mt-1.5 hidden items-center justify-between gap-4 px-1 sm:mt-2 sm:flex">
        <span class="font-latin text-[10px] font-bold tabular-nums text-muted">{{ currentPage + 1 }} / {{ totalPages }}</span>
        <div class="flex max-w-44 flex-1 gap-1" aria-label="صفحه‌های اسلایدر">
          <button v-for="page in totalPages" :key="page" type="button" class="group flex min-h-6 flex-1 items-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :aria-label="`رفتن به صفحه ${page} از ${totalPages}`" :aria-current="page - 1 === currentPage ? 'true' : undefined" @click="scrollToIndex((page - 1) * visibleCount)"><span class="h-1.5 w-full rounded-full transition-colors" :class="page - 1 === currentPage ? 'bg-primary-500' : 'bg-line group-hover:bg-disabled'" /></button>
        </div>
      </div>
    </div>
    <EmptyState v-else />
  </section>
</template>
