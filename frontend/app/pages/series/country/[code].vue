<script setup lang="ts">
const route = useRoute()
</script>

<template>
  <div>
    <CatalogLanding type="series" facet="country" :value="String(route.params.code || '')" />
  </div>
</template>
