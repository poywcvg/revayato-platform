<script setup lang="ts">
/** Minimal dependency-free sparkline. Draws an area + line from a value series. */
const props = withDefaults(defineProps<{
  values: number[]
  color?: string
  height?: number
}>(), {
  color: 'var(--rv-accent)',
  height: 40,
})

const W = 120

const geom = computed(() => {
  const vals = props.values.length ? props.values : [0, 0]
  const max = Math.max(...vals)
  const min = Math.min(...vals)
  const span = max - min || 1
  const h = props.height
  const step = W / Math.max(1, vals.length - 1)
  const pts = vals.map((v, i) => {
    const x = i * step
    const y = h - 4 - ((v - min) / span) * (h - 8)
    return [x, y] as const
  })
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${W},${h} L0,${h} Z`
  return { line, area, last: pts[pts.length - 1] }
})

const gid = `rvspark-${Math.random().toString(36).slice(2, 9)}`
</script>

<template>
  <svg :viewBox="`0 0 ${W} ${height}`" preserveAspectRatio="none" class="block w-full" :style="{ height: `${height}px` }">
    <defs>
      <linearGradient :id="gid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :stop-color="color" stop-opacity="0.28" />
        <stop offset="100%" :stop-color="color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path :d="geom.area" :fill="`url(#${gid})`" />
    <path :d="geom.line" fill="none" :stroke="color" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
    <circle v-if="geom.last" :cx="geom.last[0]" :cy="geom.last[1]" r="2.6" :fill="color" />
  </svg>
</template>
