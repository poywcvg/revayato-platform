<script setup lang="ts">
/**
 * A horizontal scroller with arrow buttons at both ends, for rows of chips,
 * tabs or cards that can outgrow the screen. Each arrow shows only while there
 * is more to see on its side, so short rows look exactly like before. Works in
 * RTL: the start arrow sits on the right and scrolls back toward the start.
 *
 * `activeKey`: when it changes, the child marked `aria-selected="true"` or
 * `.is-active` is scrolled into view (without moving the page vertically).
 */
const props = withDefaults(defineProps<{
  trackClass?: string
  role?: string
  label?: string
  activeKey?: string | number | null
  /** Share of the visible width one arrow press moves. */
  step?: number
}>(), {
  trackClass: '',
  role: undefined,
  label: undefined,
  activeKey: null,
  step: 0.8,
})

const track = ref<HTMLElement | null>(null)
const canStart = ref(false)
const canEnd = ref(false)

function isRtl() {
  return track.value ? getComputedStyle(track.value).direction === 'rtl' : true
}

function update() {
  const el = track.value
  if (!el) return
  // RTL scrollLeft runs 0 → negative in every current engine; abs() covers both.
  const offset = Math.abs(el.scrollLeft)
  canStart.value = offset > 2
  canEnd.value = offset + el.clientWidth < el.scrollWidth - 2
}

function scrollToward(side: 'start' | 'end') {
  const el = track.value
  if (!el) return
  const amount = Math.max(120, el.clientWidth * props.step)
  const forward = side === 'end' ? 1 : -1
  el.scrollBy({ left: forward * amount * (isRtl() ? -1 : 1), behavior: 'smooth' })
}

function revealActive() {
  const el = track.value
  if (!el) return
  const active = el.querySelector<HTMLElement>('[aria-selected="true"], .is-active')
  if (!active) return
  const box = el.getBoundingClientRect()
  const item = active.getBoundingClientRect()
  const pad = 24
  if (item.left < box.left + pad) el.scrollBy({ left: item.left - box.left - pad })
  else if (item.right > box.right - pad) el.scrollBy({ left: item.right - box.right + pad })
}

let observer: ResizeObserver | null = null
onMounted(() => {
  update()
  revealActive()
  if (typeof ResizeObserver !== 'undefined' && track.value) {
    observer = new ResizeObserver(update)
    observer.observe(track.value)
  }
})
onUpdated(update)
onBeforeUnmount(() => observer?.disconnect())

watch(() => props.activeKey, () => nextTick(() => { revealActive(); update() }))
</script>

<template>
  <div class="scroll-strip">
    <div
      ref="track"
      class="scroll-strip__track hide-scrollbar"
      :class="trackClass"
      :role="role"
      :aria-label="label"
      @scroll.passive="update"
    >
      <slot />
    </div>

    <button
      v-show="canStart"
      type="button"
      class="scroll-strip__arrow scroll-strip__arrow--start"
      aria-label="موارد قبلی"
      tabindex="-1"
      @click="scrollToward('start')"
    >
      <CinematicIcon name="chevron-right" class="size-4 rtl-only" />
      <CinematicIcon name="chevron-left" class="size-4 ltr-only" />
    </button>
    <button
      v-show="canEnd"
      type="button"
      class="scroll-strip__arrow scroll-strip__arrow--end"
      aria-label="موارد بعدی"
      tabindex="-1"
      @click="scrollToward('end')"
    >
      <CinematicIcon name="chevron-left" class="size-4 rtl-only" />
      <CinematicIcon name="chevron-right" class="size-4 ltr-only" />
    </button>
  </div>
</template>

<style scoped>
.scroll-strip {
  position: relative;
  min-width: 0;
}

.scroll-strip__track {
  overflow-x: auto;
  overscroll-behavior-x: contain;
}

.scroll-strip__arrow {
  position: absolute;
  z-index: 5;
  inset-block: 0;
  display: grid;
  width: 2.6rem;
  place-items: center;
  border: 0;
  padding: 0;
  color: var(--theme-text-primary);
  cursor: pointer;
}

/* No edge fade/shadow over the cards (user rule): the arrow is just its own
   solid round chip, and the strip's edges stay crisp while scrolling. */
.scroll-strip__arrow--start {
  inset-inline-start: 0;
  justify-items: start;
  background: transparent;
}

.scroll-strip__arrow--end {
  inset-inline-end: 0;
  justify-items: end;
  background: transparent;
}

.scroll-strip__arrow :deep(svg) {
  box-sizing: content-box;
  border-radius: 999px;
  background: var(--theme-bg-elevated);
  padding: 0.35rem;
  box-shadow: inset 0 0 0 1px var(--theme-border);
  transition: color 140ms ease;
}

.ltr-only { display: none; }
:dir(ltr) .rtl-only { display: none; }
:dir(ltr) .ltr-only { display: block; }

@media (hover: hover) and (pointer: fine) {
  .scroll-strip__arrow:hover :deep(svg) { color: var(--theme-accent-primary); }
}
</style>
