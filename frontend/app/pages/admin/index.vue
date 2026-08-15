<script setup lang="ts">
definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'داشبورد', robots: 'noindex, nofollow' })

// The old DB-backed `/admin` dashboard was fully merged into `/dashboard`.
onMounted(() => {
  navigateTo('/dashboard', { replace: true })
})
</script>

<template>
  <div class="grid min-h-dvh place-items-center">
    <p class="text-sm text-[var(--admin-muted)]">در حال انتقال به داشبورد…</p>
  </div>
</template>