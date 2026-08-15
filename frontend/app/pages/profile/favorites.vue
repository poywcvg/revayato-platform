<script setup lang="ts">
import { CATALOG_PAGE_SIZE, useClientPagination } from '~/composables/usePagination'

definePageMeta({ middleware: 'auth' })

const { catalog } = useCatalog()
const { likes } = useLibrary()
const items = computed(() => catalog.value.filter(item =>
  likes.value.some(entry => entry.content_type === item.type && entry.object_id === item.id),
))
const {
  page,
  totalPages,
  total,
  pageItems,
  goToPage,
} = useClientPagination(items, CATALOG_PAGE_SIZE)

useSeoMeta({ title: 'پسندیده‌ها' })
</script>

<template>
  <div class="page-section">
    <PageHero title="پسندیده‌ها" eyebrow="کتابخانه شخصی" description="فیلم‌ها و سریال‌هایی که پسندیده‌اید، در یک نمای مرتب و سریع." icon="heart" :count="total" />
    <MovieGrid :items="pageItems" empty-title="هنوز عنوانی را نپسندیده‌اید" empty-description="در صفحه جزئیات هر عنوان، دکمه پسندیدن را انتخاب کنید." />
    <CatalogPagination
      :page="page"
      :total-pages="totalPages"
      :total="total"
      label="صفحه‌بندی پسندیده‌ها"
      @change="goToPage"
    />
  </div>
</template>
