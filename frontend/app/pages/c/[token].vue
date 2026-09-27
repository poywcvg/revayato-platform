<script setup lang="ts">
import type { UserCollection } from '~/types'

const route = useRoute()
const token = computed(() => String(route.params.token || ''))
const { fetchSharedCollection } = useCollections()

const { data: collection, error } = await useAsyncData<UserCollection>(
  () => `shared-collection-${token.value}`,
  () => fetchSharedCollection(token.value),
)

if (error.value) {
  throw createError({ statusCode: 404, statusMessage: 'این کالکشن در دسترس نیست.', fatal: true })
}

useSeoMeta({
  title: () => (collection.value ? `${collection.value.title} — کالکشن ${collection.value.owner.username}` : 'کالکشن'),
  description: () => collection.value?.description || `فهرستی از ${collection.value?.item_count ?? 0} عنوان در روایتو`,
  ogTitle: () => collection.value?.title,
  ogImage: () => collection.value?.covers?.[0] || undefined,
})
</script>

<template>
  <div class="cinema-page page-section pb-14 sm:pb-20">
    <div v-if="collection" class="mb-4 flex items-center justify-between gap-3">
      <NuxtLink :to="`/u/${collection.owner.username}`" class="inline-flex items-center gap-1.5 text-sm font-bold text-secondary transition hover:text-ink">
        <CinematicIcon name="arrow-right" class="size-4" />پروفایل {{ collection.owner.username }}
      </NuxtLink>
      <NuxtLink
        v-if="collection.is_mine"
        :to="`/collections/my/${collection.slug}`"
        class="inline-flex items-center gap-1.5 rounded-xl bg-primary-500/10 px-3 py-2 text-xs font-bold text-brand transition hover:bg-primary-500/15"
      >
        <CinematicIcon name="edit" class="size-4" />مدیریت این کالکشن
      </NuxtLink>
    </div>

    <CollectionDetailView v-if="collection" :collection="collection" />
  </div>
</template>
