<script setup lang="ts">
// The day/night switch (after uiverse's theme-toggle-button): a sky pill whose
// sun slides across into a moon while the cloud gives way to stars.
// Checked = dark. It sets an explicit choice; «خودکار» lives in the profile.
const props = withDefaults(defineProps<{ size?: 'sm' | 'md' }>(), { size: 'md' })

const { isDark, toggleTheme } = useTheme()
const mounted = ref(false)
// Wait a frame so the theme resolved on mount never plays as a slide.
onMounted(() => requestAnimationFrame(() => requestAnimationFrame(() => { mounted.value = true })))

function onChange(event: Event) {
  const el = event.currentTarget as HTMLInputElement
  const box = el.parentElement?.getBoundingClientRect()
  // Keep the input in step until the theme itself flips it.
  el.checked = isDark.value
  toggleTheme(box ? { x: box.left + box.width / 2, y: box.top + box.height / 2 } : undefined)
}
</script>

<template>
  <label class="theme-toggle" :class="[`theme-toggle--${props.size}`, { 'is-ready': mounted }]" :title="isDark ? 'حالت روشن' : 'حالت تاریک'">
    <input
      type="checkbox"
      role="switch"
      class="theme-toggle__input"
      aria-label="حالت تاریک"
      :checked="isDark"
      :aria-checked="isDark"
      @change="onChange"
    >
    <svg class="theme-toggle__art" viewBox="0 0 60.667 35" aria-hidden="true" focusable="false">
      <rect class="tt-sky" rx="17.5" height="35" width="60.667" />

      <g class="tt-stars" transform="translate(3.585 1.325)">
        <path transform="matrix(-1, 0.017, -0.017, -1, 24.231, 3.055)" d="M.774,0,.566.559,0,.539.458.933.25,1.492l.485-.361.458.394L1.024.953,1.509.592.943.572Z" />
        <path transform="matrix(-0.777, 0.629, -0.629, -0.777, 23.185, 12.358)" d="M1.341.529.836.472.736,0,.505.46,0,.4.4.729l-.231.46L.605.932l.4.326L.9.786Z" />
        <path transform="matrix(0.438, 0.899, -0.899, 0.438, 23.177, 29.735)" d="M.015,1.065.475.9l.285.365L.766.772l.46-.164L.745.494.751,0,.481.407,0,.293.285.658Z" />
        <path transform="translate(12.677 0.388) rotate(104)" d="M1.161,1.6,1.059,1,1.574.722.962.607.86,0,.613.572,0,.457.446.881.2,1.454l.516-.274Z" />
        <path transform="matrix(-0.07, 0.998, -0.998, -0.07, 11.066, 15.457)" d="M.873,1.648l.114-.62L1.579.945,1.03.62,1.144,0,.706.464.157.139.438.7,0,1.167l.592-.083Z" />
        <path transform="translate(8.326 28.061) rotate(11)" d="M.593,0,.638.724,0,.982l.7.211.045.724.36-.64.7.211L1.342.935,1.7.294,1.063.552Z" />
        <path transform="translate(5.012 5.962) rotate(172)" d="M.816,0,.5.455,0,.311.323.767l-.312.455.516-.215.323.456L.827.911,1.343.7.839.552Z" />
        <path transform="translate(2.218 14.616) rotate(169)" d="M1.261,0,.774.571.114.3.487.967,0,1.538.728,1.32l.372.662.047-.749.728-.218L1.215.749Z" />
      </g>

      <g class="tt-knob">
        <g class="tt-sun">
          <circle fill="#f8e664" r="15.167" cy="15.167" cx="15.167" />
          <circle fill="rgba(246,254,247,0.29)" r="11.667" cy="15.167" cx="15.167" />
          <circle fill="#fcf4b9" r="7" cy="15.167" cx="15.167" />
        </g>
        <g class="tt-moon">
          <circle fill="#cce6ee" r="15.167" cy="15.167" cx="15.167" />
          <g fill="#a6cad0">
            <circle r="2" cx="20.594" cy="5.487" />
            <circle r="2" cx="16.951" cy="18.943" />
            <circle r="1" cx="9.601" cy="8.035" />
            <circle r="1" cx="27.666" cy="18.879" />
            <circle r="1" cx="9.601" cy="22.494" />
            <circle r="1.5" cx="27.166" cy="11.021" />
          </g>
        </g>
      </g>

      <path
        class="tt-cloud"
        fill="#fff"
        transform="translate(-3469.97 -164.44)"
        d="M3512.81,173.815a4.463,4.463,0,0,1,2.243.62.95.95,0,0,1,.72-1.281,4.852,4.852,0,0,1,2.623.519c.034.02-.5-1.968.281-2.716a2.117,2.117,0,0,1,2.829-.274,1.821,1.821,0,0,1,.854,1.858c.063.037,2.594-.049,3.285,1.273s-.865,2.544-.807,2.626a12.192,12.192,0,0,1,2.278.892c.553.448,1.106,1.992-1.62,2.927a7.742,7.742,0,0,1-3.762-.3c-1.28-.49-1.181-2.65-1.137-2.624s-1.417,2.2-2.623,2.2a4.172,4.172,0,0,1-2.394-1.206,3.825,3.825,0,0,1-2.771.774c-3.429-.46-2.333-3.267-2.2-3.55A3.721,3.721,0,0,1,3512.81,173.815Z"
      />
    </svg>
  </label>
</template>

<style scoped>
.theme-toggle {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  border-radius: 999px;
  cursor: pointer;
  /* The art is a picture of a sky, not text: always drawn left-to-right. */
  direction: ltr;
  -webkit-tap-highlight-color: transparent;
}

.theme-toggle--md { height: 2rem; }
.theme-toggle--sm { height: 1.75rem; }

.theme-toggle__input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.theme-toggle__art {
  display: block;
  height: 100%;
  width: auto;
  aspect-ratio: 60.667 / 35;
  overflow: visible;
  border-radius: 999px;
  box-shadow: inset 0 0 0 1px rgb(0 0 0 / 6%);
}

.theme-toggle:has(.theme-toggle__input:focus-visible) {
  outline: 2px solid var(--theme-accent-primary);
  outline-offset: 3px;
}

.theme-toggle:hover .theme-toggle__art { filter: brightness(1.05); }

/* Day. */
.tt-sky { fill: #83cbd8; }
.tt-knob { transform: translate(2.333px, 2.333px); }
.tt-sun, .tt-cloud { opacity: 1; }
.tt-moon, .tt-stars { opacity: 0; }
.tt-stars { fill: #def8ff; }

/* Night — keyed on the stamped theme, so the very first paint is already right. */
html[data-theme="dark"] .tt-sky { fill: #2b4360; }
html[data-theme="dark"] .tt-knob { transform: translate(28px, 2.333px); }
html[data-theme="dark"] :is(.tt-sun, .tt-cloud) { opacity: 0; }
html[data-theme="dark"] :is(.tt-moon, .tt-stars) { opacity: 1; }

/* Animate only after hydration, so the first paint never slides. */
.is-ready :is(.tt-sky, .tt-knob, .tt-sun, .tt-moon, .tt-cloud, .tt-stars) {
  transition-property: fill, transform, opacity;
  transition-duration: .25s;
  transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
}

.is-ready:active .tt-knob { transition-duration: .12s; }

@media (prefers-reduced-motion: reduce) {
  .is-ready :is(.tt-sky, .tt-knob, .tt-sun, .tt-moon, .tt-cloud, .tt-stars) { transition: none; }
}
</style>
