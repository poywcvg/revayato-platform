<script setup lang="ts">
const route = useRoute()
</script>

<template>
  <div>
    <CatalogLanding type="movie" facet="year" :value="String(route.params.year || '')" />
  </div>
</template>
