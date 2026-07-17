<script setup lang="ts">
const props = withDefaults(defineProps<{
  percent?: number
  durationMinutes?: number
  label?: string
}>(), {
  percent: 0,
  durationMinutes: 0,
  label: '',
})

const numberFormatter = new Intl.NumberFormat('fa-IR')
const normalizedPercent = computed(() => Math.min(100, Math.max(0, Math.round(props.percent))))
const remainingMinutes = computed(() => Math.max(0, Math.ceil(props.durationMinutes * (100 - normalizedPercent.value) / 100)))
</script>

<template>
  <section class="mt-3 rounded-2xl bg-white/[.035] p-3 ring-1 ring-white/10 sm:p-4" aria-label="وضعیت ادامه تماشا">
    <div class="flex items-center justify-between gap-3 text-xs">
      <div class="flex min-w-0 items-center gap-2.5">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-energy-500/10 text-energy-300 ring-1 ring-energy-400/20">
          <CinematicIcon name="resume" class="size-4" />
        </span>
        <div class="min-w-0">
          <p class="truncate font-black text-slate-100">
            {{ normalizedPercent > 0 ? `ادامه تماشا از ${numberFormatter.format(normalizedPercent)}٪` : 'آماده شروع تماشا' }}
          </p>
          <p class="mt-0.5 truncate text-[11px] text-slate-500">
            <span v-if="label">{{ label }}</span>
            <span v-if="label && remainingMinutes"> · </span>
            <span v-if="remainingMinutes">حدود {{ numberFormatter.format(remainingMinutes) }} دقیقه مانده</span>
          </p>
        </div>
      </div>
      <span class="shrink-0 font-latin font-bold tabular-nums text-primary-300">{{ normalizedPercent }}%</span>
    </div>
    <div
      class="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10"
      role="progressbar"
      aria-label="پیشرفت تماشا"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="normalizedPercent"
    >
      <div
        class="h-full rounded-full bg-primary-500 transition-[width] duration-300"
        :style="{ width: `${normalizedPercent}%` }"
      />
    </div>
  </section>
</template>
