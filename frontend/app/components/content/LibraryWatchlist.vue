<script setup lang="ts">
const { catalog } = useCatalog()
const { watchlistIds } = useLibrary()
const items = computed(() => catalog.value.filter(item => watchlistIds.value.includes(item.id)))
</script>

<template>
  <div class="page-shell py-8 sm:py-11">
    <PageHero title="لیست من" eyebrow="کتابخانه شخصی" description="عنوان‌هایی که برای تماشای بعدی ذخیره کرده‌اید، اینجا در دسترس‌اند." icon="bookmark" :count="items.length" />
    <MovieGrid v-if="items.length" :items="items" />
    <EmptyState v-else title="لیست شما خالی است" description="از صفحه فیلم‌ها یا سریال‌ها، عنوان‌های دلخواه را به لیست خود اضافه کنید." icon="bookmark" action-label="مرور فیلم‌ها" action-href="/movies" />
    <div v-if="items.length" class="ui-surface mt-9 border-primary-500/25 bg-primary-500/[.07] p-5"><div class="flex items-start gap-3"><CinematicIcon name="info" class="mt-0.5 size-5 shrink-0 text-primary-300" /><div><h2 class="text-sm font-black text-ink">ذخیره روی همین دستگاه</h2><p class="mt-1 text-xs leading-6 text-secondary">در نسخه فعلی، لیست من روی همین مرورگر ذخیره می‌شود. در نسخه بعدی با ورود به حساب، لیست روی دستگاه‌های دیگر هم در دسترس خواهد بود.</p></div></div></div>
  </div>
</template>
