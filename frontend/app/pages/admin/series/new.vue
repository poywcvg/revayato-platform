<script setup lang="ts">
definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'افزودن سریال', robots: 'noindex, nofollow' })
</script>

<template>
  <AdminContentEditor content-type="series" />
</template>
