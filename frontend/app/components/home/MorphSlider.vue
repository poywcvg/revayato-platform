<script setup lang="ts">
import type { MorphItem, MorphTransition, MorphEngineOptions } from '~/utils/morphEngine'
import { MorphEngine } from '~/utils/morphEngine'

const props = withDefaults(defineProps<{
  items?: MorphItem[]
  index?: number
  transition?: MorphTransition
  duration?: number
  ease?: string
  intensity?: number
  scale?: number
  aberration?: number
  drift?: number
  autoplay?: boolean
  autoplayDelay?: number
  loop?: boolean
  radius?: number
  overlayColor?: string
  showCaptions?: boolean
  showControls?: boolean
  showIndicators?: boolean
  className?: string
}>(), {
  items: () => [],
  index: 0,
  transition: 'melt',
  duration: 1.1,
  ease: 'power2.inOut',
  intensity: 0.55,
  scale: 2.4,
  aberration: 0.35,
  drift: 0.4,
  autoplay: false,
  autoplayDelay: 4,
  loop: true,
  radius: 16,
  overlayColor: '#05060a',
  showCaptions: false,
  showControls: false,
  showIndicators: false,
  className: '',
})

const emit = defineEmits<{
  'update:index': [index: number]
  ready: []
  error: [error: unknown]
}>()

const containerRef = useTemplateRef<HTMLDivElement>('container')
const engineRef = shallowRef<MorphEngine | null>(null)
const localIndex = ref(props.index)
const hovering = ref(false)
const ready = ref(false)

const optsRef = shallowRef<MorphEngineOptions>({
  transition: props.transition,
  duration: props.duration,
  ease: props.ease,
  intensity: props.intensity,
  scale: props.scale,
  aberration: props.aberration,
  drift: props.drift,
  overlayColor: props.overlayColor,
  loop: props.loop,
})

watchEffect(() => {
  optsRef.value = {
    transition: props.transition,
    duration: props.duration,
    ease: props.ease,
    intensity: props.intensity,
    scale: props.scale,
    aberration: props.aberration,
    drift: props.drift,
    overlayColor: props.overlayColor,
    loop: props.loop,
  }
})

const itemsKey = computed(() => props.items.map(item => item.image).join('|'))

function handleIndexChange(next: number) {
  if (next === localIndex.value) return
  localIndex.value = next
  emit('update:index', next)
}

function createEngine(startIndex: number) {
  if (!import.meta.client || !containerRef.value || !props.items.length) return
  engineRef.value?.destroy()
  engineRef.value = null
  ready.value = false
  try {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    engineRef.value = new MorphEngine(containerRef.value, {
      items: props.items,
      startIndex,
      reducedMotion,
      dprCap: 2,
      getOptions: () => optsRef.value,
      onIndexChange: handleIndexChange,
      onReady: () => {
        ready.value = true
        emit('ready')
      },
    })
    localIndex.value = startIndex
  }
  catch (error) {
    engineRef.value = null
    ready.value = false
    emit('error', error)
    if (import.meta.dev) console.warn('[MorphSlider] WebGL init failed', error)
  }
}

onMounted(() => {
  const startIndex = props.items.length
    ? Math.min(Math.max(props.index, 0), props.items.length - 1)
    : 0
  createEngine(startIndex)
})

onBeforeUnmount(() => {
  engineRef.value?.destroy()
  engineRef.value = null
})

watch(itemsKey, () => {
  const startIndex = props.items.length
    ? Math.min(Math.max(props.index, 0), props.items.length - 1)
    : 0
  createEngine(startIndex)
})

watch(() => props.index, (next) => {
  if (next === localIndex.value) return
  if (!engineRef.value) {
    localIndex.value = next
    return
  }
  localIndex.value = next
  engineRef.value.goToIndex(next)
})

watchEffect((onCleanup) => {
  if (!import.meta.client || !props.autoplay || hovering.value || props.items.length < 2) return
  const id = window.setTimeout(() => {
    engineRef.value?.next()
  }, Math.max(props.autoplayDelay, 1) * 1000)
  onCleanup(() => window.clearTimeout(id))
})

function handleNext() {
  engineRef.value?.next()
}

function handlePrev() {
  engineRef.value?.prev()
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'ArrowRight') {
    e.preventDefault()
    handleNext()
  }
  else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    handlePrev()
  }
}

const hasCaptions = computed(() => props.items.some(item => item.caption))
const focusable = computed(() => props.showControls || props.showIndicators)

defineExpose({
  ready: readonly(ready),
  next: handleNext,
  prev: handlePrev,
  goToIndex: (i: number) => engineRef.value?.goToIndex(i),
  setPointer: (x: number, y: number) => engineRef.value?.setPointer(x, y),
  beginDrag: () => engineRef.value?.beginDrag() ?? false,
  drag: (ndx: number) => engineRef.value?.drag(ndx),
  endDrag: () => engineRef.value?.endDrag(),
  pause: () => engineRef.value?.pause(),
  resume: () => engineRef.value?.resume(),
})
</script>

<template>
  <div
    class="morph-slider"
    :class="[className, ready && 'morph-slider--ready']"
    :style="{
      borderRadius: `${radius}px`,
      '--ms-swap': `${(duration * 0.66).toFixed(3)}s`,
      '--ms-dot': `${(duration * 0.45).toFixed(3)}s`,
      touchAction: 'pan-y',
    }"
    @mouseenter="hovering = true"
    @mouseleave="hovering = false"
  >
    <div
      ref="container"
      class="morph-slider__canvas"
      role="presentation"
      :tabindex="focusable ? 0 : -1"
      :aria-hidden="focusable ? undefined : true"
      @keydown="focusable ? onKeyDown($event) : undefined"
    />

    <div
      v-if="showCaptions && hasCaptions"
      class="morph-slider__captions"
      aria-live="polite"
    >
      <span
        v-for="(item, i) in items"
        v-show="item.caption"
        :key="i"
        class="morph-slider__caption"
        :class="i === localIndex ? 'morph-slider__caption--active' : undefined"
        :aria-hidden="i === localIndex ? undefined : true"
      >
        {{ item.caption }}
      </span>
    </div>

    <div v-if="showControls" class="morph-slider__controls">
      <button type="button" class="morph-slider__nav" aria-label="Previous slide" @click="handlePrev">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <button type="button" class="morph-slider__nav" aria-label="Next slide" @click="handleNext">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </div>

    <div
      v-if="showIndicators"
      class="morph-slider__indicators"
      role="tablist"
      aria-label="Slides"
    >
      <button
        v-for="(_, i) in items"
        :key="i"
        type="button"
        role="tab"
        class="morph-slider__dot"
        :class="i === localIndex && 'morph-slider__dot--active'"
        :aria-selected="i === localIndex"
        :aria-label="`Go to slide ${i + 1}`"
        @click="engineRef?.goToIndex(i)"
      />
    </div>

    <slot />
  </div>
</template>

<style scoped>
.morph-slider {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  user-select: none;
  background: transparent;
  opacity: 0;
  transition: opacity 280ms ease;
}

.morph-slider--ready {
  opacity: 1;
}

.morph-slider__canvas {
  position: absolute;
  inset: 0;
  outline: none;
}

.morph-slider :deep(.morph-engine-canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.morph-slider__captions {
  pointer-events: none;
  position: absolute;
  bottom: 22px;
  left: 22px;
  z-index: 2;
  display: grid;
  max-width: 70%;
}

.morph-slider__caption {
  pointer-events: none;
  display: inline-block;
  grid-area: 1 / 1;
  justify-self: start;
  border-radius: 10px;
  background: rgb(10 10 12 / 42%);
  padding: 8px 14px;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
  opacity: 0;
  transform: translateY(12px);
  /* GPU-composited only: opacity + transform. No filter:blur (non-composited). */
  transition:
    opacity var(--ms-swap) cubic-bezier(0.16, 1, 0.3, 1),
    transform var(--ms-swap) cubic-bezier(0.16, 1, 0.3, 1);
}

.morph-slider__caption--active {
  opacity: 1;
  transform: translateY(0);
}

.morph-slider__controls {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  z-index: 3;
  display: flex;
  justify-content: space-between;
  padding-inline: 1rem;
  pointer-events: none;
  transform: translateY(-50%);
}

.morph-slider__nav {
  pointer-events: auto;
  display: inline-flex;
  width: 2.5rem;
  height: 2.5rem;
  align-items: center;
  justify-content: center;
  border: 1px solid rgb(255 255 255 / 20%);
  border-radius: 999px;
  background: rgb(12 12 14 / 40%);
  color: #fff;
  cursor: pointer;
  backdrop-filter: blur(12px);
  transition: transform 200ms ease, background-color 200ms ease;
}

.morph-slider__nav:hover {
  transform: scale(1.05);
  background: rgb(24 24 28 / 60%);
}

.morph-slider__nav:active {
  transform: scale(0.95);
}

.morph-slider__nav:focus-visible {
  outline: 2px solid rgb(255 255 255 / 80%);
  outline-offset: 2px;
}

.morph-slider__indicators {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 18px;
  z-index: 3;
  display: flex;
  gap: 0.5rem;
  align-items: center;
  justify-content: center;
}

.morph-slider__dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  background: rgb(255 255 255 / 35%);
  cursor: pointer;
  /* GPU-composited: animate scaleX, never width (width triggers layout/reflow). */
  transform: scaleX(1);
  transform-origin: center;
  transition:
    transform var(--ms-dot) cubic-bezier(0.16, 1, 0.3, 1),
    background-color var(--ms-dot) ease;
}

.morph-slider__dot--active {
  transform: scaleX(2.75);
  background: rgb(255 255 255 / 95%);
}

.morph-slider__dot:focus-visible {
  outline: 2px solid rgb(255 255 255 / 80%);
  outline-offset: 2px;
}
</style>
