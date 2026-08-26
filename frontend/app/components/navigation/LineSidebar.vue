<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'
import type { CinematicIconName } from '~/types'

type LineSidebarFalloff = 'linear' | 'smooth' | 'sharp'

const FALLOFF_CURVES: Record<LineSidebarFalloff, (p: number) => number> = {
  linear: p => p,
  smooth: p => p * p * (3 - 2 * p),
  sharp: p => p * p * p,
}

const props = withDefaults(
  defineProps<{
    items?: string[]
    icons?: CinematicIconName[]
    direction?: 'ltr' | 'rtl'
    accentColor?: string
    textColor?: string
    markerColor?: string
    showIndex?: boolean
    showMarker?: boolean
    proximityRadius?: number
    maxShift?: number
    falloff?: LineSidebarFalloff
    markerLength?: number
    markerGap?: number
    tickScale?: number
    scaleTick?: boolean
    itemGap?: number
    fontSize?: number
    smoothing?: number
    defaultActive?: number | null
    className?: string
    /** When true, renders a magnetic mint pill that follows the pointer/finger. */
    magneticPill?: boolean
    /** Pill color (defaults to accentColor). */
    pillColor?: string
  }>(),
  {
    items: () => [
      'Overview',
      'Components',
      'Animations',
      'Backgrounds',
      'Showcase',
      'Playground',
      'Templates',
      'Changelog',
      'Community',
      'Resources',
      'Documentation',
      'Support',
    ],
    icons: () => [],
    direction: 'ltr',
    accentColor: '#A855F7',
    textColor: '#c4c4c4',
    markerColor: '#6c6c6c',
    showIndex: true,
    showMarker: true,
    proximityRadius: 100,
    maxShift: 30,
    falloff: 'smooth',
    markerLength: 60,
    markerGap: 0,
    tickScale: 0.5,
    scaleTick: true,
    itemGap: 20,
    fontSize: 1.1,
    smoothing: 100,
    defaultActive: null,
    className: '',
    magneticPill: false,
    pillColor: '',
  },
)

const emit = defineEmits<{
  itemClick: [index: number, label: string, event?: PointerEvent | MouseEvent]
  /** Fired (only when magneticPill) when the nearest item under the pointer changes. */
  magnetMove: [index: number]
}>()

const list = useTemplateRef<HTMLUListElement>('list')
const pillEl = useTemplateRef<HTMLSpanElement>('pill')
const itemEls: Array<HTMLLIElement | null> = []
const targets: number[] = []
const currents: number[] = []
const activeIndex = ref<number | null>(props.defaultActive)
let rafId: number | null = null
let lastTime = 0
let reduceMotion = false

// Magnetic pill state. The pill tracks either the live pointer position (while
// the pointer is over the list) or the active/nearest item center otherwise.
const magnetIndex = ref<number | null>(null)
let pointerActive = false
let pointerY = 0
const pillY = ref(0)
const pillMagnet = ref(0)

const resolvedPillColor = computed(() => props.pillColor || props.accentColor)

const lerp = (a: number, b: number, t: number) => a + (b - a) * t

function nearestIndex(y: number): number | null {
  let best: number | null = null
  let bestDist = Infinity
  for (let i = 0; i < itemEls.length; i++) {
    const el = itemEls[i]
    if (!el) continue
    const center = el.offsetTop + el.offsetHeight / 2
    const dist = Math.abs(center - y)
    if (dist < bestDist) {
      bestDist = dist
      best = i
    }
  }
  return best
}

// Single rAF loop that eases every item's --effect toward its target using
// frame-rate independent exponential smoothing, so color, shift and scale
// all move together without staggering CSS transitions. The magnetic pill is
// driven by the same loop so it stays in step.
function runFrame(now: number) {
  const dt = Math.min((now - lastTime) / 1000, 0.05)
  lastTime = now
  const tau = Math.max(props.smoothing, 1) / 1000
  const k = reduceMotion ? 1 : 1 - Math.exp(-dt / tau)

  let moving = false
  for (let i = 0; i < itemEls.length; i++) {
    const el = itemEls[i]
    if (!el) continue
    const target = Math.max(targets[i] || 0, activeIndex.value === i ? 1 : 0)
    const cur = currents[i] || 0
    const next = cur + (target - cur) * k
    const settled = Math.abs(target - next) < 0.0015
    const value = settled ? target : next
    currents[i] = value
    el.style.setProperty('--effect', value.toFixed(4))
    if (!settled) moving = true
  }

  if (props.magneticPill && pillEl.value) {
    let target: number
    if (pointerActive) {
      const maxH = list.value?.clientHeight ?? 0
      target = Math.max(0, Math.min(pointerY, maxH))
    } else {
      const idx = magnetIndex.value ?? activeIndex.value
      const el = idx != null ? itemEls[idx] : null
      target = el ? el.offsetTop + el.offsetHeight / 2 : pillY.value
    }
    pillY.value = lerp(pillY.value, target, k)
    pillMagnet.value = lerp(pillMagnet.value, pointerActive ? 1 : 0, k)
    pillEl.value.style.top = `${pillY.value.toFixed(2)}px`
    pillEl.value.style.setProperty('--pill-magnet', pillMagnet.value.toFixed(4))
    if (Math.abs(target - pillY.value) >= 0.5) moving = true
  }

  rafId = moving ? requestAnimationFrame(runFrame) : null
}

function startLoop() {
  if (rafId != null) cancelAnimationFrame(rafId)
  lastTime = performance.now()
  rafId = requestAnimationFrame(runFrame)
}

function handlePointerMove(event: PointerEvent) {
  const root = list.value
  if (!root) return
  const rect = root.getBoundingClientRect()
  pointerActive = true
  pointerY = event.clientY - rect.top
  const ease = FALLOFF_CURVES[props.falloff] ?? FALLOFF_CURVES.linear
  const radius = Math.max(props.proximityRadius, 1)
  for (let i = 0; i < itemEls.length; i++) {
    const el = itemEls[i]
    if (!el) continue
    const center = el.offsetTop + el.offsetHeight / 2
    const distance = Math.abs(pointerY - center)
    targets[i] = ease(Math.max(0, 1 - distance / radius))
  }
  if (props.magneticPill) {
    const near = nearestIndex(pointerY)
    if (near != null && near !== magnetIndex.value) {
      magnetIndex.value = near
      emit('magnetMove', near)
    }
  }
  startLoop()
}

function handlePointerLeave() {
  pointerActive = false
  targets.fill(0)
  startLoop()
}

function handleFocusIn(event: FocusEvent) {
  if (!props.magneticPill) return
  const target = event.target as HTMLElement | null
  const li = target?.closest<HTMLLIElement>('.line-sidebar__item')
  if (!li) return
  const idx = itemEls.indexOf(li)
  if (idx >= 0 && idx !== magnetIndex.value) {
    magnetIndex.value = idx
    emit('magnetMove', idx)
    pointerActive = false
    startLoop()
  }
}

function handleClick(index: number, label: string, event?: PointerEvent | MouseEvent) {
  activeIndex.value = index
  if (props.magneticPill) magnetIndex.value = index
  emit('itemClick', index, label, event)
}

function setItemRef(el: Element | ComponentPublicInstance | null, index: number) {
  itemEls[index] = el instanceof HTMLLIElement ? el : null
}

watch(activeIndex, startLoop)
watch(
  () => props.defaultActive,
  (next) => {
    activeIndex.value = next
  },
)

onMounted(() => {
  reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (props.magneticPill) {
    const idx = activeIndex.value ?? 0
    const el = itemEls[idx]
    if (el) pillY.value = el.offsetTop + el.offsetHeight / 2
  }
  startLoop()
})

onBeforeUnmount(() => {
  if (rafId != null) cancelAnimationFrame(rafId)
  rafId = null
})
</script>

<template>
  <nav
    class="line-sidebar"
    :class="[showMarker && 'line-sidebar--markers', scaleTick && 'line-sidebar--scale-tick', className]"
    :dir="direction"
    :style="{
      '--accent-color': accentColor,
      '--text-color': textColor,
      '--marker-color': markerColor,
      '--marker-length': `${markerLength}px`,
      '--marker-gap': `${markerGap}px`,
      '--tick-scale': tickScale,
      '--max-shift': `${maxShift}px`,
      '--item-gap': `${itemGap}px`,
      '--font-size': `${fontSize}rem`,
      '--smoothing': `${smoothing}ms`,
      '--pill-color': resolvedPillColor,
    }"
  >
    <ul
      ref="list"
      class="line-sidebar__list"
      @pointermove="handlePointerMove"
      @pointerleave="handlePointerLeave"
      @focusin="handleFocusIn"
    >
      <span
        v-if="magneticPill"
        ref="pill"
        class="line-sidebar__magnet-pill"
        aria-hidden="true"
      />
      <li
        v-for="(label, index) in items"
        :key="`${label}-${index}`"
        :ref="el => setItemRef(el, index)"
        class="line-sidebar__item"
        @click="handleClick(index, label, $event)"
      >
        <span v-if="showMarker" class="line-sidebar__marker" aria-hidden="true" />
        <button type="button" class="line-sidebar__control" :aria-current="activeIndex === index ? 'true' : undefined">
          <span class="line-sidebar__label">
            <span v-if="icons[index]" class="line-sidebar__icon" aria-hidden="true">
              <CinematicIcon :name="icons[index] || 'home'" />
            </span>
            <span v-if="showIndex" class="line-sidebar__index">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="line-sidebar__text">{{ label }}</span>
          </span>
        </button>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.line-sidebar {
  --accent-color: #a855f7;
  --text-color: #c4c4c4;
  --marker-color: #6c6c6c;
  --marker-length: 60px;
  --marker-gap: 0px;
  --tick-scale: 0.5;
  --max-shift: 30px;
  --item-gap: 20px;
  --font-size: 1.1rem;
  --smoothing: 100ms;
  --shift-direction: var(--max-shift);
  --pill-color: var(--accent-color);

  position: relative;
  display: flex;
  justify-content: flex-start;
}

.line-sidebar[dir='rtl'] {
  --shift-direction: calc(-1 * var(--max-shift));
}

.line-sidebar--markers {
  padding-inline-start: calc(var(--marker-length) + var(--marker-gap));
}

.line-sidebar__list {
  position: relative;
  list-style: none;
  margin: 0;
  padding: 1rem 0;
  display: flex;
  flex-direction: column;
  gap: var(--item-gap);
}

/* --effect (0..1) is driven per item by a rAF lerp in JS, so every derived
   property below reads the same continuously-animating value and stays in
   step, with no CSS transitions to stagger. */
.line-sidebar__item {
  position: relative;
  z-index: 1;
  cursor: pointer;
}

.line-sidebar__control {
  display: block;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: inherit;
  cursor: inherit;
  outline: none;
}

.line-sidebar__control:focus-visible {
  border-radius: 0.25rem;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent-color) 65%, transparent);
}

/* Widen the pointer target so items react a touch before the cursor arrives */
.line-sidebar__item::before {
  content: '';
  position: absolute;
  inset: -6px -48px;
}

.line-sidebar__label {
  position: relative;
  display: inline-flex;
  align-items: center;
  font-size: var(--font-size);
  line-height: 1.2;
  color: color-mix(in srgb, var(--accent-color) calc(var(--effect, 0) * 100%), var(--text-color));
  transform: translateX(calc(var(--effect, 0) * var(--shift-direction)));
}

.line-sidebar__icon {
  display: inline-grid;
  width: 1.35em;
  height: 1.35em;
  flex: none;
  place-items: center;
  margin-inline-end: 0.6rem;
}

.line-sidebar__icon :deep(svg) {
  width: 100%;
  height: 100%;
}

.line-sidebar__index {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  margin-inline-end: 0.6rem;
  font-size: 0.85em;
  opacity: calc(0.55 + var(--effect, 0) * 0.45);
}

.line-sidebar__marker {
  position: absolute;
  top: 50%;
  inset-inline-start: calc(-1 * var(--marker-length) - var(--marker-gap));
  height: 1px;
  width: var(--marker-length);
  background-color: color-mix(in srgb, var(--accent-color) calc(var(--effect, 0) * 100%), var(--marker-color));
  transform-origin: left center;
  transform: translateY(-50%) scaleX(calc(0.7 + var(--effect, 0) * 0.5));
}

.line-sidebar[dir='rtl'] .line-sidebar__marker {
  transform-origin: right center;
}

/* Short static tick centered in the gap between two menu items */
.line-sidebar--markers .line-sidebar__item:not(:last-child)::after {
  content: '';
  position: absolute;
  top: calc(100% + var(--item-gap) / 2);
  inset-inline-start: calc(-1 * var(--marker-length) - var(--marker-gap));
  height: 1px;
  width: calc(var(--marker-length) * var(--tick-scale));
  background-color: var(--marker-color);
  opacity: 0.5;
  transform: translateY(-50%);
}

.line-sidebar[dir='rtl'] .line-sidebar__item:not(:last-child)::after {
  transform-origin: right center;
}

/* When enabled, the in-between ticks grow with cursor proximity too */
.line-sidebar--scale-tick .line-sidebar__item:not(:last-child)::after {
  transform-origin: left center;
  transform: translateY(-50%) scaleX(calc(0.7 + var(--effect, 0) * 0.6));
}

/* Magnetic mint pill that liquid-follows the pointer / focused item. */
.line-sidebar__magnet-pill {
  position: absolute;
  inset-inline: 0.35rem;
  top: 0;
  height: calc(var(--touch-target, 44px) * 0.9);
  z-index: 0;
  pointer-events: none;
  border-radius: 0.95rem;
  border: 1px solid color-mix(in srgb, var(--pill-color) 34%, transparent);
  background:
    radial-gradient(130% 150% at 50% 0%, color-mix(in srgb, var(--pill-color) 18%, transparent), transparent 70%),
    color-mix(in srgb, var(--pill-color) 9%, var(--theme-bg-elevated, #141414));
  box-shadow:
    inset 0 1px 0 color-mix(in srgb, var(--pill-color) 24%, transparent),
    inset 0 0 18px color-mix(in srgb, var(--pill-color) 8%, transparent);
  transform: translateY(-50%) scale(calc(1 + var(--pill-magnet, 0) * 0.03));
  transition: opacity 0.25s ease;
}

.line-sidebar__magnet-pill::before {
  content: '';
  position: absolute;
  inset-inline-start: 0.55rem;
  top: 50%;
  width: 0.32rem;
  height: 1.5rem;
  border-radius: 9999px;
  background: var(--pill-color);
  transform: translateY(-50%) scaleY(calc(0.5 + var(--pill-magnet, 0) * 0.5));
  transform-origin: center;
  box-shadow: 0 0 12px color-mix(in srgb, var(--pill-color) 75%, transparent);
}

:global(html[data-theme='light'] .line-sidebar__magnet-pill) {
  border-color: color-mix(in srgb, var(--pill-color) 44%, transparent);
  background:
    radial-gradient(130% 150% at 50% 0%, color-mix(in srgb, var(--pill-color) 22%, transparent), transparent 70%),
    color-mix(in srgb, var(--pill-color) 14%, var(--theme-bg-elevated, #f1f5f3));
}
</style>
