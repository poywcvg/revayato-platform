<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

const { catalog } = useCatalog()
const { likedIds } = useLibrary()
const items = computed(() => catalog.value.filter(item => likedIds.value.includes(item.id)))
useSeoMeta({ title: 'پسندیده‌ها' })
</script>

<template>
  <div class="page-shell py-8 sm:py-11">
    <PageHero title="پسندیده‌ها" eyebrow="کتابخانه شخصی" description="فیلم‌ها و سریال‌هایی که پسندیده‌اید، در یک نمای مرتب و سریع." icon="heart" :count="items.length" />
    <MovieGrid :items="items" empty-title="هنوز عنوانی را نپسندیده‌اید" empty-description="در صفحه جزئیات هر عنوان، دکمه پسندیدن را انتخاب کنید." />
  </div>
</template>
