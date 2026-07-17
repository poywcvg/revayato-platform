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
  <div v-else class="grid grid-cols-2 gap-3.5 sm:grid-cols-3 sm:gap-5 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
    <MovieCard v-for="(item, index) in items" :key="item.id" :item="item" :priority="index < 2" />
  </div>
</template>
