<script setup lang="ts">
definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'ویرایش سریال', robots: 'noindex, nofollow' })
const route = useRoute()
const seriesId = Number(route.params.id)
if (!Number.isInteger(seriesId) || seriesId <= 0) throw createError({ statusCode: 404, message: 'سریال پیدا نشد.' })
</script>

<template>
  <AdminContentEditor content-type="series" :item-id="seriesId" />
</template>
