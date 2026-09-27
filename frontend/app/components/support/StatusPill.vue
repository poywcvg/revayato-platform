<script setup lang="ts">
import type { SupportStatus } from '~/types'
import { SUPPORT_STATUS_META } from '~/composables/useSupport'

const props = withDefaults(defineProps<{ status: SupportStatus, size?: 'sm' | 'md' }>(), {
  size: 'md',
})

const meta = computed(() => SUPPORT_STATUS_META[props.status] ?? SUPPORT_STATUS_META.open)

// Tone → concrete Tailwind classes (kept literal so the JIT compiler sees them).
const TONE_CLASS: Record<string, string> = {
  sky: 'bg-sky-500/12 text-sky-300 ring-sky-500/25',
  amber: 'bg-amber-500/12 text-amber-300 ring-amber-500/25',
  violet: 'bg-violet-500/14 text-violet-300 ring-violet-500/30',
  emerald: 'bg-emerald-500/12 text-emerald-300 ring-emerald-500/25',
  zinc: 'bg-white/6 text-muted ring-white/12',
}
</script>

<template>
  <span
    class="inline-flex items-center gap-1 rounded-full font-black ring-1"
    :class="[TONE_CLASS[meta.tone] || TONE_CLASS.sky, size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs']"
  >
    <CinematicIcon :name="meta.icon" :class="size === 'sm' ? 'size-3' : 'size-3.5'" />
    {{ meta.label }}
  </span>
</template>
