<script setup lang="ts">
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import type { ComposeOption } from 'echarts/core'
import type { PieSeriesOption } from 'echarts/charts'
import type { TooltipComponentOption, LegendComponentOption } from 'echarts/components'

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent])

type ECOption = ComposeOption<PieSeriesOption | TooltipComponentOption | LegendComponentOption>

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  slices: Array<{ label: string, value: number }>
  loading?: boolean
}>(), {
  title: '',
  subtitle: '',
  loading: false,
})

const colors = ['#285a48', '#408a71', '#2563eb', '#b45309', '#7c3aed']

const option = computed<ECOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'item',
    backgroundColor: '#fff',
    borderColor: 'rgba(40,90,72,0.14)',
    textStyle: { color: '#091413', fontFamily: 'Vazirmatn, sans-serif', fontSize: 12 },
  },
  legend: {
    bottom: 0,
    textStyle: { color: '#5a7268', fontFamily: 'Vazirmatn, sans-serif', fontSize: 11 },
  },
  series: [{
    type: 'pie',
    radius: ['46%', '70%'],
    center: ['50%', '44%'],
    avoidLabelOverlap: true,
    itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
    label: { show: false },
    data: props.slices.map((slice, index) => ({
      name: slice.label,
      value: slice.value,
      itemStyle: { color: colors[index % colors.length] },
    })),
  }],
}))

const empty = computed(() => !props.slices.some(slice => slice.value > 0))
</script>

<template>
  <AdminCard class="overflow-hidden">
    <div v-if="title || subtitle" class="border-b border-[var(--admin-border)] px-4 py-3 sm:px-5">
      <h3 v-if="title" class="text-sm font-black text-[var(--admin-text)]">{{ title }}</h3>
      <p v-if="subtitle" class="mt-0.5 text-[11px] text-[var(--admin-muted)]">{{ subtitle }}</p>
    </div>
    <div class="p-3 sm:p-4">
      <div v-if="loading" class="grid h-56 place-items-center">
        <div class="size-36 animate-pulse rounded-full bg-[var(--admin-surface-muted)]" />
      </div>
      <div v-else-if="empty" class="grid h-56 place-items-center text-sm text-[var(--admin-muted)]">
        هنوز دادهٔ دستگاه ثبت نشده
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
