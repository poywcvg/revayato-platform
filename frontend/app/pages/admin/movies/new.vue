<script setup lang="ts">
definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'افزودن فیلم جدید', robots: 'noindex, nofollow' })
</script>

<template>
  <AdminContentEditor content-type="movie" />
</template>
