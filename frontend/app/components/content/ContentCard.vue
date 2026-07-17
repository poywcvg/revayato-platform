<script setup lang="ts">
import type { Movie } from '~/types'
defineProps<{ item: Movie }>()
</script>

<template>
  <MovieCard :item="item" />
</template>
