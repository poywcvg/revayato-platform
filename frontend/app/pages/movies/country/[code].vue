<script setup lang="ts">
const route = useRoute()
</script>

<template>
  <div>
    <CatalogLanding type="movie" facet="country" :value="String(route.params.code || '')" />
  </div>
</template>
