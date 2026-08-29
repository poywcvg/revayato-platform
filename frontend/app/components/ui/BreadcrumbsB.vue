<script setup lang="ts">
import type { CinematicIconName } from '~/types'

export type BreadcrumbItem = {
  icon?: CinematicIconName
  slug?: string
  title?: string | number
  href?: string
  iconOnly?: boolean
  active?: boolean
}

const props = withDefaults(defineProps<{
  items: BreadcrumbItem[]
  separator?: 'bar' | 'arrow' | 'circle'
  highlightLastItem?: boolean
  size?: 'small' | 'medium' | 'large'
  variant?: 'default' | 'blue' | 'red' | 'blue-outline'
}>(), {
  separator: 'arrow',
  highlightLastItem: true,
  size: 'medium',
  variant: 'default',
})

const wrapperClasses = computed(() => [
  `breadcrumbs-b--${props.size}`,
  `breadcrumbs-b--${props.variant}`,
  { 'breadcrumbs-b--highlight-last': props.highlightLastItem },
])
</script>

<template>
  <nav class="breadcrumbs-b" :class="wrapperClasses" aria-label="مسیر صفحه">
    <ol v-if="items.length" class="breadcrumbs-b__list">
      <li
        v-for="(item, index) in items"
        :key="item.slug || `${String(item.title)}-${index}`"
        class="breadcrumbs-b__item"
        :class="{ 'is-active': item.active }"
      >
        <NuxtLink
          v-if="item.href"
          class="breadcrumbs-b__link"
          :to="item.href"
          :aria-label="item.iconOnly ? String(item.title || '') : undefined"
        >
          <span class="breadcrumbs-b__item-wrapper">
            <CinematicIcon v-if="item.icon" :name="item.icon" class="breadcrumbs-b__icon" />
            <span v-if="!item.iconOnly" class="breadcrumbs-b__content">{{ item.title }}</span>
          </span>
        </NuxtLink>
        <span
          v-else
          class="breadcrumbs-b__item-wrapper"
          :aria-current="item.active || index === items.length - 1 ? 'page' : undefined"
        >
          <CinematicIcon v-if="item.icon" :name="item.icon" class="breadcrumbs-b__icon" />
          <span v-if="!item.iconOnly" class="breadcrumbs-b__content">{{ item.title }}</span>
        </span>

        <span v-if="index < items.length - 1" class="breadcrumbs-b__separator" aria-hidden="true">
          <slot name="separator">
            <svg v-if="separator === 'arrow'" viewBox="0 0 16 16"><path d="m10.85 7.65-5-5a.5.5 0 0 0-.7.7L9.79 8l-4.64 4.65a.5.5 0 0 0 .7.7l5-5a.5.5 0 0 0 0-.7Z" fill="currentColor" /></svg>
            <svg v-else-if="separator === 'bar'" viewBox="0 0 16 16"><rect x="10.74" y="2" width="1" height="12.95" rx=".5" transform="rotate(26.32 10.74 2)" fill="currentColor" /></svg>
            <svg v-else viewBox="0 0 16 16"><circle cx="8" cy="8" r="3" fill="currentColor" /></svg>
          </slot>
        </span>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.breadcrumbs-b {
  --crumb-accent: var(--theme-accent-primary);
  --crumb-bg: color-mix(in srgb, var(--theme-bg-surface) 78%, transparent);
  max-width: 100%;
  color: var(--theme-text-muted);
}
.breadcrumbs-b__list { display: flex; min-width: 0; flex-wrap: wrap; align-items: center; gap: .25rem; }
.breadcrumbs-b__item { display: inline-flex; min-width: 0; align-items: center; gap: .25rem; }
.breadcrumbs-b__item-wrapper { display: inline-flex; min-width: 0; align-items: center; gap: .4rem; border-radius: .7rem; padding: .45rem .55rem; }
.breadcrumbs-b__link { border-radius: .7rem; color: var(--theme-text-secondary); transition: color 160ms ease, background-color 160ms ease; }
.breadcrumbs-b__link:hover { background: var(--crumb-bg); color: var(--crumb-accent); }
.breadcrumbs-b__link:focus-visible { outline: 2px solid var(--crumb-accent); outline-offset: 2px; }
.breadcrumbs-b__content { max-width: min(13rem, 42vw); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.breadcrumbs-b__icon { width: 1em; height: 1em; flex: none; }
.breadcrumbs-b__separator { display: grid; flex: none; place-items: center; color: var(--theme-text-disabled); }
.breadcrumbs-b__separator svg { width: 1em; height: 1em; }
.breadcrumbs-b--small { font-size: .68rem; font-weight: 700; }
.breadcrumbs-b--medium { font-size: .75rem; font-weight: 700; }
.breadcrumbs-b--large { font-size: .875rem; font-weight: 700; }
.breadcrumbs-b--highlight-last .breadcrumbs-b__item:last-child,
.breadcrumbs-b__item.is-active { color: var(--theme-text-primary); }
.breadcrumbs-b--blue { --crumb-accent: var(--theme-info); }
.breadcrumbs-b--red { --crumb-accent: var(--theme-accent-crimson); }
.breadcrumbs-b--blue-outline { --crumb-accent: var(--theme-info); padding: .3rem; border: 1px solid color-mix(in srgb, var(--theme-info) 35%, transparent); border-radius: .9rem; }
@media (prefers-reduced-motion: reduce) { .breadcrumbs-b__link { transition: none; } }
</style>
