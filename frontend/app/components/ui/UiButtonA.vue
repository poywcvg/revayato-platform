<script setup lang="ts">
/**
 * Shared brand action button (uiverse-inspired, adapted to the theme tokens).
 * A diagonal light streak sweeps across on hover, the surface lifts a hair, and
 * a press settles it back — one motion vocabulary for every CTA on the site.
 *
 * Renders a <button> by default, a <NuxtLink> when `to` is set, or an <a> when
 * `href` is set, so it drops in wherever a plain button/link is today.
 */
const props = withDefaults(defineProps<{
  variant?: 'primary' | 'ghost' | 'danger' | 'telegram'
  size?: 'sm' | 'md' | 'lg'
  to?: string
  href?: string
  type?: 'button' | 'submit' | 'reset'
  block?: boolean
  loading?: boolean
  disabled?: boolean
}>(), {
  variant: 'primary',
  size: 'md',
  type: 'button',
  block: false,
  loading: false,
  disabled: false,
})

const tag = computed(() => (props.to ? resolveComponent('NuxtLink') : props.href ? 'a' : 'button'))

const rootClasses = computed(() => [
  `ui-btn-a--${props.variant}`,
  `ui-btn-a--${props.size}`,
  { 'ui-btn-a--block': props.block, 'ui-btn-a--loading': props.loading },
])

const bindings = computed(() => {
  if (props.to) return { to: props.to }
  if (props.href) return { href: props.href }
  return { type: props.type, disabled: props.disabled || props.loading }
})
</script>

<template>
  <component
    :is="tag"
    class="ui-btn-a"
    :class="rootClasses"
    :aria-busy="loading ? 'true' : undefined"
    :aria-disabled="disabled || loading ? 'true' : undefined"
    v-bind="bindings"
  >
    <span class="ui-btn-a__shine" aria-hidden="true" />
    <span v-if="loading" class="ui-btn-a__spinner" aria-hidden="true">
      <span v-for="n in 10" :key="n" class="ui-btn-a__blade" :style="{ '--rotation': n * 36, '--delay': n / 10 }" />
    </span>
    <span class="ui-btn-a__content"><slot /></span>
  </component>
</template>

<style scoped>
.ui-btn-a {
  --btn-fill: var(--theme-accent-primary);
  --btn-fill-strong: var(--theme-accent-primary-hover, var(--theme-accent-primary));
  --btn-ink: var(--theme-bg-main);
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: .85rem;
  font-weight: 800;
  line-height: 1;
  white-space: nowrap;
  text-decoration: none;
  cursor: pointer;
  isolation: isolate;
  transition: transform 180ms cubic-bezier(.22, 1, .36, 1), box-shadow 200ms ease, background-color 180ms ease, border-color 180ms ease, color 180ms ease;
}
.ui-btn-a:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--btn-fill) 80%, transparent);
  outline-offset: 2px;
}
.ui-btn-a:active { transform: translateY(1px) scale(.985); }

/* Diagonal light streak that sweeps across on hover. */
.ui-btn-a__shine {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background: linear-gradient(115deg, transparent 30%, rgb(255 255 255 / 38%) 50%, transparent 70%);
  transform: translateX(-140%);
  transition: transform 620ms cubic-bezier(.22, 1, .36, 1);
}
.ui-btn-a:hover .ui-btn-a__shine,
.ui-btn-a:focus-visible .ui-btn-a__shine { transform: translateX(140%); }

.ui-btn-a__content {
  position: relative;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: .5rem;
  transition: opacity 160ms ease;
}

/* Sizes */
.ui-btn-a--sm { min-height: 2.1rem; padding-inline: .85rem; font-size: .78rem; }
.ui-btn-a--md { min-height: 2.6rem; padding-inline: 1.15rem; font-size: .85rem; }
.ui-btn-a--lg { min-height: 3.1rem; padding-inline: 1.6rem; font-size: .95rem; border-radius: 1rem; }
.ui-btn-a--block { width: 100%; }

/* Primary — solid brand fill. */
.ui-btn-a--primary {
  background: var(--btn-fill);
  color: var(--btn-ink);
  box-shadow: none;
}
.ui-btn-a--primary:hover {
  background: var(--btn-fill-strong);
  transform: translateY(-1px);
  box-shadow: none;
}

/* Ghost — quiet ring that warms to the brand tint. */
.ui-btn-a--ghost {
  background: color-mix(in srgb, var(--theme-bg-elevated) 92%, transparent);
  border-color: var(--theme-border);
  color: var(--theme-text-secondary);
}
.ui-btn-a--ghost .ui-btn-a__shine { background: linear-gradient(115deg, transparent 30%, color-mix(in srgb, var(--btn-fill) 22%, transparent) 50%, transparent 70%); }
.ui-btn-a--ghost:hover {
  border-color: color-mix(in srgb, var(--btn-fill) 55%, var(--theme-border));
  color: var(--theme-text-primary);
  transform: translateY(-1px);
}

/* Danger — crimson intent. */
.ui-btn-a--danger {
  --btn-fill: var(--theme-accent-crimson, var(--theme-error));
  background: var(--btn-fill);
  color: #fff;
  box-shadow: none;
}
.ui-btn-a--danger:hover { transform: translateY(-1px); box-shadow: none; }

/* Telegram — the brand's channel blue. */
.ui-btn-a--telegram {
  --btn-fill: #2aabee;
  background: color-mix(in srgb, #2aabee 12%, var(--theme-bg-elevated));
  border-color: color-mix(in srgb, #2aabee 34%, var(--theme-border));
  color: var(--theme-text-primary);
}
.ui-btn-a--telegram:hover { background: color-mix(in srgb, #2aabee 20%, var(--theme-bg-elevated)); transform: translateY(-1px); }

/* Loading — reuses the brand blade spinner, content fades but holds width. */
.ui-btn-a--loading { pointer-events: none; }
.ui-btn-a--loading .ui-btn-a__content { opacity: 0; }
.ui-btn-a__spinner {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-items: center;
}
.ui-btn-a__blade {
  position: absolute;
  top: calc(50% - .5em);
  left: calc(50% - .12em);
  width: .24em;
  height: .5em;
  border-radius: 999px;
  background: currentColor;
  transform: rotate(calc(var(--rotation) * 1deg)) translate(0, -.55em);
  animation: ui-btn-a-ripple 1s calc(var(--delay) * 1s) infinite ease;
}
@keyframes ui-btn-a-ripple {
  0%, 40%, 100% { opacity: .35; transform: rotate(calc(var(--rotation) * 1deg)) translate(0, -.55em) scale(.85); }
  20% { opacity: 1; transform: rotate(calc(var(--rotation) * 1deg)) translate(0, -.8em) scale(1); }
}

.ui-btn-a[aria-disabled='true'] { opacity: .55; cursor: not-allowed; transform: none; box-shadow: none; }

@media (prefers-reduced-motion: reduce) {
  .ui-btn-a, .ui-btn-a__shine, .ui-btn-a__content { transition-duration: 1ms; }
  .ui-btn-a:hover { transform: none; }
  .ui-btn-a__shine { display: none; }
  .ui-btn-a__blade { animation-duration: 2.4s; }
}
</style>
