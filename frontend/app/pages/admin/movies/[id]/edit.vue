<script setup lang="ts">
definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'ویرایش فیلم', robots: 'noindex, nofollow' })
const route = useRoute()
const movieId = Number(route.params.id)
if (!Number.isInteger(movieId) || movieId <= 0) throw createError({ statusCode: 404, message: 'فیلم پیدا نشد.' })
</script>

<template><AdminContentEditor content-type="movie" :item-id="movieId" /></template>
