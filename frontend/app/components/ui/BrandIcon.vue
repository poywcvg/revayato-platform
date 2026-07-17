<script setup lang="ts">
import type { BrandIconName } from '~/types'

interface IconCircle {
  cx: number
  cy: number
  r: number
}

interface IconDefinition {
  paths: string[]
  accentPaths?: string[]
  fillPaths?: string[]
  circles?: IconCircle[]
  accentCircles?: IconCircle[]
}

const props = withDefaults(defineProps<{
  name: BrandIconName
  title?: string
  duotone?: boolean
  strokeWidth?: number
}>(), {
  title: '',
  duotone: true,
  strokeWidth: 1.8,
})

const icons: Record<BrandIconName, IconDefinition> = {
  brand: {
    paths: ['M7 4.75h7.8a4.45 4.45 0 0 1 4.45 4.45v5.6a4.45 4.45 0 0 1-4.45 4.45H7A2.25 2.25 0 0 1 4.75 17V7A2.25 2.25 0 0 1 7 4.75Z', 'm10.15 8.35 5.25 3.65-5.25 3.65Z'],
    accentPaths: ['M4.85 8.15A7.9 7.9 0 0 0 5 16.2'],
    accentCircles: [{ cx: 5.15, cy: 7.15, r: 0.85 }],
  },
  home: {
    paths: ['M4.25 10.4 12 4.35l7.75 6.05v7.35a1.9 1.9 0 0 1-1.9 1.9H6.15a1.9 1.9 0 0 1-1.9-1.9Z', 'M9 19.65V14h6v5.65'],
    accentPaths: ['M7.25 10.85h9.5'],
  },
  search: {
    paths: ['M10.45 4.2a6.25 6.25 0 1 0 0 12.5 6.25 6.25 0 0 0 0-12.5Z', 'm15.05 15.05 4.65 4.65'],
    accentPaths: ['M6.75 8.2a4.1 4.1 0 0 1 1.75-1.55'],
    accentCircles: [{ cx: 17.8, cy: 6.2, r: 1 }],
  },
  movie: {
    paths: ['M4 6.1A2.1 2.1 0 0 1 6.1 4h11.8A2.1 2.1 0 0 1 20 6.1v11.8a2.1 2.1 0 0 1-2.1 2.1H6.1A2.1 2.1 0 0 1 4 17.9Z', 'm10.25 8.5 5 3.5-5 3.5Z'],
    accentPaths: ['M4.2 7h2.2m11.2 0h2.2M4.2 17h2.2m11.2 0h2.2'],
  },
  series: {
    paths: ['M6.2 7h11.6A2.2 2.2 0 0 1 20 9.2v8.6a2.2 2.2 0 0 1-2.2 2.2H6.2A2.2 2.2 0 0 1 4 17.8V9.2A2.2 2.2 0 0 1 6.2 7Z', 'M7 4h10'],
    accentPaths: ['m10.2 10.2 4.5 3.05-4.5 3.05Z'],
    accentCircles: [{ cx: 18.8, cy: 4, r: 0.8 }],
  },
  animation: {
    paths: ['M6.1 8.2h11.8a2.1 2.1 0 0 1 2.1 2.1v7.6a2.1 2.1 0 0 1-2.1 2.1H6.1A2.1 2.1 0 0 1 4 17.9v-7.6a2.1 2.1 0 0 1 2.1-2.1Z', 'm12 10.4 1.05 2.15 2.35.35-1.7 1.65.4 2.35-2.1-1.1-2.1 1.1.4-2.35-1.7-1.65 2.35-.35Z'],
    accentPaths: ['M7 5.8 5.8 4.5M17 5.8l1.2-1.3'],
  },
  trend: {
    paths: ['M4 18.8V6.2', 'M4 17.7 8.1 13l3.15 2.3L17.9 7.5'],
    accentPaths: ['M14.7 7.5h3.2v3.2'],
    accentCircles: [{ cx: 8.1, cy: 13, r: 0.9 }, { cx: 11.25, cy: 15.3, r: 0.9 }],
  },
  ai: {
    paths: ['M12 3.4c.65 4.65 2.85 6.85 7.5 7.5-4.65.65-6.85 2.85-7.5 7.5-.65-4.65-2.85-6.85-7.5-7.5 4.65-.65 6.85-2.85 7.5-7.5Z'],
    accentPaths: ['M5.2 5.2a9.6 9.6 0 0 1 3.1-1.65'],
    accentCircles: [{ cx: 4.25, cy: 6.1, r: 0.8 }, { cx: 19.2, cy: 18.1, r: 1 }],
  },
  resume: {
    paths: ['M5.15 8.1A7.65 7.65 0 1 1 4.7 15', 'M5.15 8.1V4.7M5.15 8.1h3.4', 'm10.1 8.6 5 3.4-5 3.4Z'],
    accentPaths: ['M5.8 17.4a8.2 8.2 0 0 1-1.1-2.4'],
  },
  bookmark: {
    paths: ['M7.1 4h9.8A2.1 2.1 0 0 1 19 6.1v14l-7-4.25L5 20.1v-14A2.1 2.1 0 0 1 7.1 4Z'],
    accentPaths: ['M8.1 7.25h7.8'],
  },
  profile: {
    paths: ['M12 4.2a3.55 3.55 0 1 0 0 7.1 3.55 3.55 0 0 0 0-7.1Z', 'M5.1 19.8c.55-4.15 2.85-6.2 6.9-6.2s6.35 2.05 6.9 6.2'],
    accentPaths: ['M8.05 18.7c.75-1.55 2.05-2.3 3.95-2.3'],
  },
  play: {
    paths: ['M12 3.75a8.25 8.25 0 1 1-7.55 4.9', 'm9.65 8.15 5.7 3.85-5.7 3.85Z'],
    accentPaths: ['M4.45 8.65A8.1 8.1 0 0 1 6.6 5.8'],
    accentCircles: [{ cx: 7.3, cy: 5.15, r: 0.75 }],
  },
  info: {
    paths: ['M12 3.75a8.25 8.25 0 1 0 0 16.5 8.25 8.25 0 0 0 0-16.5Z', 'M12 10.6v5.2'],
    accentCircles: [{ cx: 12, cy: 7.6, r: 1 }],
  },
  trailer: {
    paths: ['M4 9h16v8.8a2.2 2.2 0 0 1-2.2 2.2H6.2A2.2 2.2 0 0 1 4 17.8Z', 'M4.5 5.1 18.9 3.5l.45 4-14.4 1.6Z', 'm10.3 12 4.4 2.55-4.4 2.55Z'],
    accentPaths: ['m8 4.7 2.2 3.7m3.1-4.25 2.2 3.7'],
  },
  mood: {
    paths: ['M16.9 4.7a7.7 7.7 0 1 0 2.35 10.95A6.8 6.8 0 0 1 16.9 4.7Z'],
    accentPaths: ['M5.1 6.4 6 4.8l.9 1.6 1.6.9-1.6.9L6 9.8l-.9-1.6-1.6-.9Z'],
  },
  settings: {
    paths: ['M4 6.5h16M4 12h16M4 17.5h16'],
    accentCircles: [{ cx: 8, cy: 6.5, r: 1.5 }, { cx: 15.5, cy: 12, r: 1.5 }, { cx: 10.5, cy: 17.5, r: 1.5 }],
  },
  star: {
    paths: ['m12 3.8 2.35 4.75 5.25.76-3.8 3.7.9 5.23L12 15.78l-4.7 2.46.9-5.23-3.8-3.7 5.25-.76Z'],
    accentPaths: ['M18.1 4.6v2.6m-1.3-1.3h2.6'],
  },
  heart: {
    paths: ['M12 20S4.3 15.45 4.3 9.55A4.15 4.15 0 0 1 12 7.4a4.15 4.15 0 0 1 7.7 2.15C19.7 15.45 12 20 12 20Z'],
    accentPaths: ['M7.1 10.1a2.2 2.2 0 0 1 2-2.25'],
  },
  audio: {
    paths: ['M5 10h3.1l4-3.3v10.6l-4-3.3H5Z', 'M15.1 9.1a4 4 0 0 1 0 5.8', 'M17.5 6.8a7.2 7.2 0 0 1 0 10.4'],
    accentCircles: [{ cx: 19.8, cy: 5.3, r: 0.8 }],
  },
  subtitle: {
    paths: ['M4 5.2h16v12.6A2.2 2.2 0 0 1 17.8 20H6.2A2.2 2.2 0 0 1 4 17.8Z', 'M7 15.8h4.1M13 15.8h4M7 12.2h6'],
    accentPaths: ['M15 12.2h2'],
  },
  quality: {
    paths: ['M4.2 18.8a8.1 8.1 0 0 1 15.6 0', 'M7.25 18.8a5 5 0 0 1 9.5 0', 'M10.4 18.8a1.8 1.8 0 0 1 3.2 0'],
    accentPaths: ['M12 5.2v3.2'],
    accentCircles: [{ cx: 12, cy: 4.1, r: 0.8 }],
  },
  exciting: {
    paths: ['m13.3 3.8-7 9.25h5.05L10.7 20l7-9.25h-5.05Z'],
    accentPaths: ['M5 6.2 6.2 5M18 18.5l1.2-1.2'],
  },
  calm: {
    paths: ['M5.2 15.8a4 4 0 0 1 1.15-7.82A5.75 5.75 0 0 1 17.45 9.7a3.1 3.1 0 0 1 .2 6.1Z', 'M7 19h10'],
    accentPaths: ['M8 5.9a5.8 5.8 0 0 1 4-1.55'],
  },
  scary: {
    paths: ['M3.8 12s3-5.5 8.2-5.5 8.2 5.5 8.2 5.5-3 5.5-8.2 5.5S3.8 12 3.8 12Z', 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z'],
    accentPaths: ['M4.9 7.1 6.4 8m11.2 0 1.5-.9'],
  },
  thoughtful: {
    paths: ['M8.1 14.6a6.1 6.1 0 1 1 7.8 0c-.85.65-1.25 1.35-1.25 2.1h-5.3c0-.75-.4-1.45-1.25-2.1Z', 'M9.5 20h5'],
    accentPaths: ['M12 3V1.8M5.4 5.7l-.9-.9m13.1.9.9-.9'],
  },
  family: {
    paths: ['M8.2 6.2a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8Zm7.6 1.3a2.1 2.1 0 1 0 0 4.2 2.1 2.1 0 0 0 0-4.2ZM3.9 19c.35-3.65 1.8-5.45 4.3-5.45s3.95 1.8 4.3 5.45m.2-4.5c.75-.4 1.8-.55 3.1-.45 2.4.2 3.75 1.85 4.05 4.95'],
    accentPaths: ['M10.8 13.2a6.1 6.1 0 0 1 2.35-.95'],
  },
  light: {
    paths: ['M12 4.1a7.9 7.9 0 1 0 7.9 7.9A7.9 7.9 0 0 0 12 4.1Z', 'M12 7.4v4.9l3.2 1.8'],
    accentPaths: ['M5.25 4.8 6.4 5.95M18.75 4.8 17.6 5.95'],
  },
}

const icon = computed(() => icons[props.name])
</script>

<template>
  <svg
    class="brand-icon"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    :role="title ? 'img' : undefined"
    :aria-hidden="title ? undefined : 'true'"
    :aria-label="title || undefined"
    :style="duotone ? undefined : '--brand-icon-accent: currentColor'"
  >
    <title v-if="title">{{ title }}</title>
    <g class="brand-icon__main" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <path v-for="path in icon.paths" :key="path" :d="path" />
      <circle v-for="circle in icon.circles" :key="`${circle.cx}-${circle.cy}-${circle.r}`" :cx="circle.cx" :cy="circle.cy" :r="circle.r" />
    </g>
    <g v-if="icon.fillPaths?.length" fill="currentColor">
      <path v-for="path in icon.fillPaths" :key="path" :d="path" />
    </g>
    <g class="brand-icon__accent" stroke="var(--brand-icon-accent, currentColor)" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <path v-for="path in icon.accentPaths" :key="path" :d="path" />
      <circle v-for="circle in icon.accentCircles" :key="`${circle.cx}-${circle.cy}-${circle.r}`" :cx="circle.cx" :cy="circle.cy" :r="circle.r" fill="var(--brand-icon-accent, currentColor)" stroke="none" />
    </g>
  </svg>
</template>

<style scoped>
.brand-icon {
  display: inline-block;
  flex: none;
  overflow: visible;
}

.brand-icon__accent {
  opacity: .92;
  transform-origin: center;
  transition: opacity 160ms ease, transform 160ms ease;
}

:global(.group:hover) .brand-icon__accent {
  opacity: 1;
  transform: scale(1.035);
}

@media (prefers-reduced-motion: reduce) {
  .brand-icon__accent { transition: none; }
}
</style>
