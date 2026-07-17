<script setup lang="ts">
import type { Movie } from '~/types'
withDefaults(defineProps<{ item: Movie; priority?: boolean; dark?: boolean; reason?: string }>(), { priority: false, dark: false, reason: '' })
</script>

<template>
  <CinematicCard :item="item" :priority="priority" :reason="reason" />
</template>
