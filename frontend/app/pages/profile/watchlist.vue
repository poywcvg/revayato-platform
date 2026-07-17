<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

useSeoMeta({ title: 'لیست من' })
</script>

<template>
  <LibraryWatchlist />
</template>
