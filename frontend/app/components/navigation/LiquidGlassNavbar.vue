<script setup lang="ts">
import type { LiquidNavItem } from '~/types'

const props = withDefaults(defineProps<{
  items: LiquidNavItem[]
  variant?: 'desktop' | 'mobile'
  label?: string
}>(), {
  variant: 'desktop',
  label: 'ناوبری اصلی',
})

const route = useRoute()
const root = useTemplateRef<HTMLElement>('root')
const indicator = reactive({ x: 0, width: 0, visible: false })
const isReady = ref(false)
let resizeObserver: ResizeObserver | undefined
let measureFrame = 0
let readyFrame = 0

function itemPath(item: LiquidNavItem) {
  return item.to.split(/[?#]/, 1)[0] || '/'
}

function isActive(item: LiquidNavItem) {
  const path = itemPath(item)
  if (item.exact || path === '/') return route.path === path
  return route.path === path || route.path.startsWith(`${path}/`)
}

const activeIndex = computed(() => props.items.findIndex(isActive))

function positionIndicator() {
  cancelAnimationFrame(measureFrame)
  measureFrame = requestAnimationFrame(() => {
    const container = root.value
    const target = container?.querySelector<HTMLElement>(`[data-liquid-index="${activeIndex.value}"]`)
    if (!container || !target) {
      indicator.visible = false
      return
    }
    const containerRect = container.getBoundingClientRect()
    const targetRect = target.getBoundingClientRect()
    indicator.x = targetRect.left - containerRect.left
    indicator.width = targetRect.width
    indicator.visible = true

    // The first paint should appear in place; subsequent route changes slide.
    if (!isReady.value) {
      cancelAnimationFrame(readyFrame)
      readyFrame = requestAnimationFrame(() => { isReady.value = true })
    }
  })
}

const indicatorStyle = computed(() => ({
  width: `${indicator.width}px`,
  transform: `translate3d(${indicator.x}px, 0, 0)`,
  opacity: indicator.visible ? '1' : '0',
}))

watch(
  [
    () => route.fullPath,
    () => props.variant,
    () => props.items.map(item => `${item.to}:${item.label}`).join('|'),
  ],
  async () => {
    await nextTick()
    positionIndicator()
  },
  { flush: 'post' },
)

onMounted(async () => {
  await nextTick()
  positionIndicator()
  if ('ResizeObserver' in window && root.value) {
    resizeObserver = new ResizeObserver(positionIndicator)
    resizeObserver.observe(root.value)
  }
  window.addEventListener('resize', positionIndicator, { passive: true })
  document.fonts?.ready.then(() => positionIndicator()).catch(() => {})
})

onBeforeUnmount(() => {
  cancelAnimationFrame(measureFrame)
  cancelAnimationFrame(readyFrame)
  resizeObserver?.disconnect()
  window.removeEventListener('resize', positionIndicator)
})
</script>

<template>
  <nav
    ref="root"
    class="liquid-nav"
    :class="[`liquid-nav--${variant}`, { 'liquid-nav--ready': isReady }]"
    :aria-label="label"
    dir="rtl"
  >
    <span class="liquid-nav__shine" aria-hidden="true" />
    <span class="liquid-nav__indicator" :style="indicatorStyle" aria-hidden="true" />
    <NuxtLink
      v-for="(item, index) in items"
      :key="`${item.to}-${item.label}`"
      :data-liquid-index="index"
      :to="item.to"
      class="liquid-nav__item"
      :class="isActive(item) && 'liquid-nav__item--active'"
      :title="item.label"
      :aria-current="isActive(item) ? 'page' : undefined"
    >
      <span class="liquid-nav__icon-wrap">
        <CinematicIcon
          :name="item.icon"
          class="liquid-nav__icon"
          :filled="isActive(item) && item.icon === 'bookmark'"
          :stroke-width="isActive(item) ? 2.2 : 1.8"
        />
        <span v-if="item.badge" class="liquid-nav__badge">{{ item.badge > 99 ? '۹۹+' : item.badge.toLocaleString('fa-IR') }}</span>
      </span>
      <span class="liquid-nav__label">{{ item.label }}</span>
    </NuxtLink>
  </nav>
</template>

<style scoped>
/* Nav glass built from the site palette: void / soft / mint. */
.liquid-nav {
  --glass-deep: var(--palette-void-rgb);
  --glass-primary: 14 22 20;
  --glass-accent: var(--palette-deep-rgb);
  --glass-warm: var(--palette-sand-rgb);
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  padding: 5px;
  overflow: hidden;
  border: 1px solid rgb(var(--glass-warm) / 14%);
  border-radius: 9999px;
  background: color-mix(in srgb, var(--theme-bg-elevated) 55%, transparent);
  box-shadow:
    0 14px 36px var(--theme-shadow),
    inset 0 1px 0 rgb(var(--glass-warm) / 10%),
    inset 0 -1px 0 rgb(0 0 0 / 24%);
  color: color-mix(in srgb, var(--theme-text-secondary) 88%, var(--theme-accent-primary));
  -webkit-backdrop-filter: blur(10px) saturate(120%);
  backdrop-filter: blur(10px) saturate(120%);
}

.liquid-nav--desktop { min-height: 54px; gap: 1px; }
.liquid-nav--mobile { width: 100%; min-height: 56px; justify-content: stretch; gap: 1px; padding: 5px 6px; }

.liquid-nav__shine {
  position: absolute;
  z-index: -1;
  inset: 1px 10% auto;
  height: 45%;
  border-radius: 9999px;
  background: linear-gradient(180deg, rgb(var(--glass-warm) / 12%), transparent);
  pointer-events: none;
}

.liquid-nav__indicator {
  position: absolute;
  z-index: -1;
  top: 5px;
  bottom: 5px;
  left: 0;
  border: 1px solid rgb(var(--glass-warm) / 28%);
  border-radius: 9999px;
  background: var(--theme-accent-primary-soft);
  box-shadow:
    0 4px 14px var(--theme-shadow),
    inset 0 1px 0 rgb(var(--glass-warm) / 18%);
  opacity: 0;
  pointer-events: none;
  will-change: transform, width;
}

.liquid-nav--ready .liquid-nav__indicator {
  transition:
    transform 420ms cubic-bezier(.22, 1, .36, 1),
    width 420ms cubic-bezier(.22, 1, .36, 1),
    opacity 140ms ease;
}

.liquid-nav__item {
  position: relative;
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 12px;
  border-radius: 9999px;
  color: inherit;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  transition: color 180ms ease, background-color 180ms ease, transform 180ms ease;
  -webkit-tap-highlight-color: transparent;
}

.liquid-nav__item:active { transform: scale(.975); }
.liquid-nav__item--active { color: var(--theme-accent-primary); text-shadow: none; }
.liquid-nav__item:focus-visible { outline: 2px solid var(--theme-accent-primary); outline-offset: -2px; }
.liquid-nav__icon-wrap { position: relative; display: grid; place-items: center; }
.liquid-nav__icon { width: 17px; height: 17px; flex: none; }
.liquid-nav__badge {
  position: absolute;
  top: -9px;
  inset-inline-end: -10px;
  display: grid;
  min-width: 16px;
  height: 16px;
  place-items: center;
  padding: 0 4px;
  border: 2px solid var(--theme-bg-elevated);
  border-radius: 9999px;
  background: var(--theme-accent-primary);
  color: var(--theme-bg-main);
  font-size: 8px;
  font-weight: 600;
  line-height: 1;
}

.liquid-nav--mobile .liquid-nav__item {
  min-width: 44px;
  min-height: 50px;
  flex: 1 1 0;
  flex-direction: column;
  gap: 2px;
  padding: 3px 2px 2px;
  font-size: 9px;
  line-height: 1.25;
}
.liquid-nav--mobile .liquid-nav__icon { width: 19px; height: 19px; }
.liquid-nav--mobile .liquid-nav__label {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (hover: hover) and (pointer: fine) {
  .liquid-nav__item:hover {
    color: var(--theme-accent-primary-hover);
    background: var(--theme-accent-primary-soft);
  }
}

@supports not ((-webkit-backdrop-filter: blur(1px)) or (backdrop-filter: blur(1px))) {
  .liquid-nav { background: var(--theme-bg-elevated); }
}

/* Tablet / small desktop: icons only so the bar never overflows the header. */
@media (min-width: 1024px) and (max-width: 1279px) {
  .liquid-nav--desktop .liquid-nav__item {
    gap: 0;
    padding-inline: 11px;
  }

  .liquid-nav--desktop .liquid-nav__label {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .liquid-nav--desktop .liquid-nav__icon {
    width: 18px;
    height: 18px;
  }
}

@media (min-width: 1280px) and (max-width: 1439px) {
  .liquid-nav--desktop .liquid-nav__item {
    gap: 5px;
    padding-inline: 10px;
    font-size: 11px;
  }
}

@media (max-width: 380px) {
  .liquid-nav--mobile .liquid-nav__label { font-size: 8px; }
  .liquid-nav--mobile .liquid-nav__item { padding-inline: 1px; }
}

@media (prefers-reduced-motion: reduce) {
  .liquid-nav__indicator,
  .liquid-nav__item { transition: none; }

  .liquid-nav__item:active { transform: none; }
}

:global(html[data-theme="light"] .liquid-nav) {
  background: color-mix(in srgb, var(--theme-bg-surface) 94%, transparent);
  border-color: var(--theme-border);
  box-shadow:
    0 10px 26px rgb(23 50 38 / 8%),
    inset 0 1px 0 rgb(255 255 255 / 85%);
  color: var(--theme-text-secondary);
}

:global(html[data-theme="light"] .liquid-nav__indicator) {
  background: var(--theme-surface-selected);
  border-color: color-mix(in srgb, var(--theme-accent-primary) 34%, var(--theme-border));
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 70%);
}

:global(html[data-theme="light"] .liquid-nav__badge) {
  border-color: var(--theme-bg-surface);
  background: var(--theme-accent-primary);
  color: var(--theme-on-accent);
}
</style>
