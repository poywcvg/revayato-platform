<script setup lang="ts">
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import type { AnalyticsHeatmapCell } from '~/types/analytics'

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent])

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  weekdays: Array<{ id: number, label: string }>
  hours: number[]
  cells: AnalyticsHeatmapCell[]
  loading?: boolean
}>(), {
  title: '',
  subtitle: '',
  loading: false,
})

const option = computed(() => {
  const weekdayIndex = new Map(props.weekdays.map((day, index) => [day.id, index]))
  const data = props.cells.map(cell => [
    cell.hour,
    weekdayIndex.get(cell.weekday) ?? 0,
    cell.value,
  ])
  const max = Math.max(1, ...props.cells.map(cell => cell.value))
  return {
    backgroundColor: 'transparent',
    tooltip: {
      position: 'top',
      backgroundColor: '#fff',
      borderColor: 'rgba(40,90,72,0.14)',
      textStyle: { color: '#091413', fontFamily: 'Vazirmatn, sans-serif', fontSize: 12 },
      formatter: (params: { value?: number[] }) => {
        const value = params.value || []
        const hour = value[0]
        const day = props.weekdays[value[1] || 0]?.label || ''
        return `${day} · ساعت ${String(hour).padStart(2, '0')}<br/>${(value[2] || 0).toLocaleString('fa-IR')} رویداد`
      },
    },
    grid: { left: 72, right: 20, top: 12, bottom: 48 },
    xAxis: {
      type: 'category',
      data: props.hours.map(hour => String(hour).padStart(2, '0')),
      splitArea: { show: true },
      axisLabel: { color: '#5a7268', fontSize: 9 },
    },
    yAxis: {
      type: 'category',
      data: props.weekdays.map(day => day.label),
      axisLabel: { color: '#5a7268', fontSize: 10 },
    },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#e8f4ee', '#b0e4cc', '#408a71', '#285a48'] },
      textStyle: { color: '#5a7268' },
    },
    series: [{
      type: 'heatmap',
      data,
      emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(40,90,72,0.25)' } },
    }],
  }
})
</script>

<template>
  <AdminCard class="overflow-hidden">
    <div v-if="title || subtitle" class="border-b border-[var(--admin-border)] px-4 py-3 sm:px-5">
      <h3 v-if="title" class="text-sm font-black text-[var(--admin-text)]">{{ title }}</h3>
      <p v-if="subtitle" class="mt-0.5 text-[11px] text-[var(--admin-muted)]">{{ subtitle }}</p>
    </div>
    <div class="p-3 sm:p-4">
      <div v-if="loading" class="h-64 animate-pulse rounded-xl bg-[var(--admin-surface-muted)]" />
      <ClientOnly v-else>
        <VChart class="h-64 w-full" :option="option" autoresize />
        <template #fallback>
          <div class="h-64 animate-pulse rounded-xl bg-[var(--admin-surface-muted)]" />
        </template>
      </ClientOnly>
    </div>
  </AdminCard>
</template>
