<script setup lang="ts">
const route = useRoute()
</script>

<template>
  <div>
    <CatalogLanding type="series" facet="genre" :value="String(route.params.slug || '')" />
  </div>
</template>
