<script setup lang="ts">
import type { AgeRating } from "~/types";
defineProps<{ rating: AgeRating; showLabel?: boolean }>();
</script>

<template>
  <span
    class="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-black shadow-sm ring-1 ring-inset"
    :class="
      rating === '18+'
        ? 'bg-error/90 text-ink ring-error'
        : rating === '15+'
          ? 'bg-warning text-canvas ring-warning'
          : 'bg-success/90 text-canvas ring-success'
    "
  >
    <span v-if="showLabel" class="font-bold opacity-80">رده سنی</span
    >{{ rating }}
  </span>
</template>
