<script setup lang="ts">
const route = useRoute()

useSeoMeta({ title: String(route.params.username) })
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-16 text-center">
    <CinematicIcon name="user" class="mx-auto mb-4 size-16 text-slate-300" />
    <h1 class="mb-2 text-xl font-bold text-ink">پروفایل {{ route.params.username }}</h1>
    <p class="text-slate-500">نمایش عمومی پروفایل کاربران به‌زودی راه‌اندازی می‌شود.</p>
  </div>
</template>
