<script setup lang="ts">
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart as ELineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import type { ComposeOption } from 'echarts/core'
import type { LineSeriesOption } from 'echarts/charts'
import type { GridComponentOption, TooltipComponentOption } from 'echarts/components'

use([CanvasRenderer, ELineChart, GridComponent, TooltipComponent])

type ECOption = ComposeOption<LineSeriesOption | GridComponentOption | TooltipComponentOption>

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  labels: string[]
  values: number[]
  loading?: boolean
  color?: string
  area?: boolean
}>(), {
  title: '',
  subtitle: '',
  loading: false,
  color: '#285a48',
  area: true,
})

const option = computed<ECOption>(() => ({
  backgroundColor: 'transparent',
  grid: { left: 44, right: 18, top: 24, bottom: 32 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#fff',
    borderColor: 'rgba(40,90,72,0.14)',
    textStyle: { color: '#091413', fontFamily: 'Vazirmatn, sans-serif', fontSize: 12 },
  },
  xAxis: {
    type: 'category',
    data: props.labels,
    axisLine: { lineStyle: { color: 'rgba(40,90,72,0.18)' } },
    axisLabel: { color: '#5a7268', fontSize: 10 },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: 'rgba(40,90,72,0.08)' } },
    axisLabel: { color: '#5a7268', fontSize: 10 },
  },
  series: [{
    type: 'line',
    smooth: true,
    showSymbol: props.values.length <= 14,
    symbolSize: 6,
    data: props.values,
    lineStyle: { width: 2.5, color: props.color },
    itemStyle: { color: props.color },
    areaStyle: props.area
      ? {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(40,90,72,0.22)' },
              { offset: 1, color: 'rgba(40,90,72,0.02)' },
            ],
          },
        }
      : undefined,
  }],
}))
</script>

<template>
  <AdminCard class="overflow-hidden">
    <div v-if="title || subtitle" class="border-b border-[var(--admin-border)] px-4 py-3 sm:px-5">
      <h3 v-if="title" class="text-sm font-black text-[var(--admin-text)]">{{ title }}</h3>
      <p v-if="subtitle" class="mt-0.5 text-[11px] text-[var(--admin-muted)]">{{ subtitle }}</p>
    </div>
    <div class="p-3 sm:p-4">
      <div v-if="loading" class="flex h-56 animate-pulse items-end gap-2 px-2">
        <div v-for="n in 12" :key="n" class="flex-1 rounded-t bg-[var(--admin-surface-muted)]" :style="{ height: `${30 + (n % 5) * 12}%` }" />
      </div>
      <ClientOnly v-else>
        <VChart class="h-56 w-full" :option="option" autoresize />
        <template #fallback>
          <div class="h-56 animate-pulse rounded-xl bg-[var(--admin-surface-muted)]" />
        </template>
      </ClientOnly>
    </div>
  </AdminCard>
</template>
