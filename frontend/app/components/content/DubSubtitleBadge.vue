<script setup lang="ts">
withDefaults(defineProps<{
  isDubbed?: boolean
  hasSubtitle?: boolean
  /** Icon-only pills for dense surfaces like home cards. */
  iconsOnly?: boolean
  compact?: boolean
  dark?: boolean
}>(), {
  isDubbed: false,
  hasSubtitle: false,
  iconsOnly: false,
  compact: false,
  dark: false,
})
</script>

<template>
  <span v-if="isDubbed || hasSubtitle" class="inline-flex flex-wrap items-center gap-1.5">
    <span
      v-if="isDubbed"
      class="inline-flex items-center justify-center rounded-lg ring-1 ring-inset"
      :class="[
        iconsOnly ? 'size-7 bg-primary-500/14 text-primary-300 ring-primary-400/25' : 'gap-1 bg-primary-500/14 px-2 py-1 text-[10px] font-black text-primary-300 ring-primary-400/25',
      ]"
      :title="iconsOnly ? 'دوبله فارسی' : undefined"
      :aria-label="iconsOnly ? 'دوبله فارسی' : undefined"
    >
      <CinematicIcon name="audio" :class="iconsOnly ? 'size-3.5' : 'size-3.5'" />
      <span v-if="!iconsOnly">{{ compact ? 'دوبله' : 'دوبله فارسی' }}</span>
    </span>
    <span
      v-if="hasSubtitle"
      class="inline-flex items-center justify-center rounded-lg ring-1 ring-inset"
      :class="[
        iconsOnly
          ? (dark ? 'size-7 bg-white/5 text-secondary ring-white/10' : 'size-7 bg-elevated text-secondary ring-line')
          : (dark ? 'gap-1 bg-white/5 px-2 py-1 text-[10px] font-black text-secondary ring-white/10' : 'gap-1 bg-elevated px-2 py-1 text-[10px] font-black text-secondary ring-line'),
      ]"
      :title="iconsOnly ? 'زیرنویس فارسی' : undefined"
      :aria-label="iconsOnly ? 'زیرنویس فارسی' : undefined"
    >
      <CinematicIcon name="subtitle" class="size-3.5" />
      <span v-if="!iconsOnly">{{ compact ? 'زیرنویس' : 'زیرنویس فارسی' }}</span>
    </span>
  </span>
</template>
