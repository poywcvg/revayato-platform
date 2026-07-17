<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

useSeoMeta({ title: 'لیست من', description: 'فیلم‌ها و سریال‌های ذخیره‌شده برای تماشای بعدی.' })
</script>

<template>
  <LibraryWatchlist />
</template>
