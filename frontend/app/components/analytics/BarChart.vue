<script setup lang="ts">
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart as EBarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import type { ComposeOption } from 'echarts/core'
import type { BarSeriesOption } from 'echarts/charts'
import type { GridComponentOption, TooltipComponentOption } from 'echarts/components'

use([CanvasRenderer, EBarChart, GridComponent, TooltipComponent])

type ECOption = ComposeOption<BarSeriesOption | GridComponentOption | TooltipComponentOption>

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  labels: string[]
  values: number[]
  loading?: boolean
  color?: string
  horizontal?: boolean
}>(), {
  title: '',
  subtitle: '',
  loading: false,
  color: '#285a48',
  horizontal: false,
})

const option = computed<ECOption>(() => ({
  backgroundColor: 'transparent',
  grid: { left: props.horizontal ? 100 : 44, right: 18, top: 20, bottom: 32 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#fff',
    borderColor: 'rgba(40,90,72,0.14)',
    textStyle: { color: '#091413', fontFamily: 'Vazirmatn, sans-serif', fontSize: 12 },
  },
  xAxis: props.horizontal
    ? {
        type: 'value',
        splitLine: { lineStyle: { color: 'rgba(40,90,72,0.08)' } },
        axisLabel: { color: '#5a7268', fontSize: 10 },
      }
    : {
        type: 'category',
        data: props.labels,
        axisLine: { lineStyle: { color: 'rgba(40,90,72,0.18)' } },
        axisLabel: { color: '#5a7268', fontSize: 10 },
      },
  yAxis: props.horizontal
    ? {
        type: 'category',
        data: props.labels,
        axisLine: { lineStyle: { color: 'rgba(40,90,72,0.18)' } },
        axisLabel: { color: '#5a7268', fontSize: 10 },
      }
    : {
        type: 'value',
        splitLine: { lineStyle: { color: 'rgba(40,90,72,0.08)' } },
        axisLabel: { color: '#5a7268', fontSize: 10 },
      },
  series: [{
    type: 'bar',
    data: props.values,
    barMaxWidth: 26,
    itemStyle: {
      color: props.color,
      borderRadius: props.horizontal ? [0, 8, 8, 0] : [8, 8, 0, 0],
    },
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
        <div v-for="n in 8" :key="n" class="flex-1 rounded-t bg-[var(--admin-surface-muted)]" :style="{ height: `${25 + (n % 4) * 15}%` }" />
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
