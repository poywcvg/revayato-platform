<script setup lang="ts">
import type { Movie } from '~/types'
withDefaults(defineProps<{ items: Movie[]; loading?: boolean; emptyTitle?: string; emptyDescription?: string }>(), {
  loading: false,
  emptyTitle: 'نتیجه‌ای پیدا نشد',
  emptyDescription: 'فیلترها را تغییر دهید یا عبارت دیگری را جستجو کنید.',
})
</script>

<template>
  <LoadingSkeleton v-if="loading" :count="12" />
  <EmptyState v-else-if="!items.length" :title="emptyTitle" :description="emptyDescription" icon="search" />
  <div v-else class="catalog-grid">
    <MovieCard v-for="(item, index) in items" :key="`${item.type}-${item.id}`" :item="item" :priority="index < 4" />
  </div>
</template>
