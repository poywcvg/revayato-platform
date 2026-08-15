<script setup lang="ts">
import { CATALOG_PAGE_SIZE, useClientPagination } from '~/composables/usePagination'

const { catalog } = useCatalog()
const { watchlist } = useLibrary()
const items = computed(() => catalog.value.filter(item =>
  watchlist.value.some(entry => entry.content_type === item.type && entry.object_id === item.id),
))
const {
  page,
  totalPages,
  total,
  pageItems,
  goToPage,
} = useClientPagination(items, CATALOG_PAGE_SIZE)
</script>

<template>
  <div class="page-section">
    <PageHero title="لیست من" eyebrow="کتابخانه شخصی" description="عنوان‌هایی که برای تماشای بعدی ذخیره کرده‌اید، اینجا در دسترس‌اند." icon="bookmark" :count="total" />
    <MovieGrid v-if="pageItems.length" :items="pageItems" />
    <EmptyState v-else title="لیست شما خالی است" description="از صفحه فیلم‌ها یا سریال‌ها، عنوان‌های دلخواه را به لیست خود اضافه کنید." icon="bookmark" action-label="مرور فیلم‌ها" action-href="/movies" />
    <CatalogPagination
      :page="page"
      :total-pages="totalPages"
      :total="total"
      label="صفحه‌بندی لیست من"
      @change="goToPage"
    />
    <div v-if="total" class="ui-surface mt-9 border-primary-500/25 bg-primary-500/[.07] p-5">
      <div class="flex items-start gap-3">
        <CinematicIcon name="info" class="mt-0.5 size-5 shrink-0 text-primary-300" />
        <div>
          <h2 class="text-sm font-black text-ink">همگام با حساب کاربری</h2>
          <p class="mt-1 text-xs leading-6 text-secondary">لیست من روی حساب تو ذخیره می‌شود و بعد از ورود روی دستگاه‌های دیگر هم در دسترس است.</p>
        </div>
      </div>
    </div>
  </div>
</template>
