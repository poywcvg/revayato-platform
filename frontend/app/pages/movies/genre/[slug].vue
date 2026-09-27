<script setup lang="ts">
const route = useRoute()
</script>

<template>
  <div>
    <CatalogLanding type="movie" facet="genre" :value="String(route.params.slug || '')" />
  </div>
</template>
