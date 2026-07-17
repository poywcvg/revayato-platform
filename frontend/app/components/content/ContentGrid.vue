<script setup lang="ts">
import type { Movie } from '~/types'
withDefaults(defineProps<{ items: Movie[]; title: string; viewAllHref?: string; loading?: boolean; eyebrow?: string }>(), {
  viewAllHref: '',
  loading: false,
  eyebrow: '',
})
</script>

<template>
  <section class="content-section">
    <SectionHeader :title="title" :eyebrow="eyebrow" :href="viewAllHref" />
    <MovieGrid :items="items" :loading="loading" />
  </section>
</template>
