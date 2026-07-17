<script setup lang="ts">
withDefaults(defineProps<{
  label?: string
  compact?: boolean
}>(), {
  label: 'تصویر در دسترس نیست',
  compact: false,
})
</script>

<template>
  <div class="cinematic-image-fallback absolute inset-0 grid place-items-center p-4 text-center" role="img" :aria-label="label">
    <div class="relative z-10 flex flex-col items-center">
      <span class="grid size-12 place-items-center rounded-2xl bg-white/[.055] text-primary-400 ring-1 ring-white/10 shadow-inner" :class="compact && 'size-10 rounded-xl'">
        <CinematicIcon name="image-off" :class="compact ? 'size-5' : 'size-6'" />
      </span>
      <span v-if="!compact" class="mt-3 max-w-36 text-[11px] font-bold leading-5 text-slate-400">{{ label }}</span>
    </div>
  </div>
</template>

