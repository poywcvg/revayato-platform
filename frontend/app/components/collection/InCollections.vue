<script setup lang="ts">
import type { ContentType } from '~/types'

/**
 * Discovery rail on a movie/series detail page: the PUBLIC collections that
 * real users have built and dropped this title into. Honest data only — it
 * renders nothing until the fetch resolves with at least one collection, so a
 * title nobody has collected shows no empty shell.
 */
const props = defineProps<{
  contentType: ContentType
  objectId: number
  title: string
}>()

const { fetchPublicContaining } = useCollections()

const { data, pending } = await useAsyncData(
  () => `title-collections-${props.contentType}-${props.objectId}`,
  () => fetchPublicContaining(props.contentType, props.objectId),
  { watch: [() => props.objectId, () => props.contentType], server: false, lazy: true },
)

const collections = computed(() => data.value?.results ?? [])
const total = computed(() => data.value?.count ?? 0)
const hasMore = computed(() => total.value > collections.value.length)
const countLabel = computed(() => total.value.toLocaleString('fa-IR'))
</script>

<template>
  <section
    v-if="pending || collections.length"
    id="in-collections"
    class="in-collections"
    aria-label="کالکشن‌هایی که این عنوان در آن‌هاست"
  >
    <ContentSectionHeader
      title="در این کالکشن‌ها هست"
      eyebrow="ساختهٔ کاربران روایتو"
      icon="layers"
      :description="`${title} را کاربران در ${countLabel} کالکشن عمومی کنار عنوان‌های دیگر گذاشته‌اند.`"
    />

    <div v-if="pending && !collections.length" class="in-collections__loading">
      <div v-for="n in 4" :key="n" class="in-collections__skeleton" />
    </div>

    <ul v-else class="in-collections__grid">
      <li v-for="collection in collections" :key="collection.id">
        <CollectionSummaryCard :collection="collection" :to="collection.share_url" />
      </li>
    </ul>

    <p v-if="hasMore" class="in-collections__more">
      و {{ (total - collections.length).toLocaleString('fa-IR') }} کالکشن دیگر
    </p>
  </section>
</template>

<style scoped>
.in-collections {
  margin-top: 0.5rem;
}

.in-collections__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 15rem), 1fr));
  gap: 0.9rem;
  list-style: none;
  padding: 0;
  margin: 0;
}

.in-collections__loading {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 15rem), 1fr));
  gap: 0.9rem;
}

.in-collections__skeleton {
  aspect-ratio: 16 / 13;
  border-radius: 1.1rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 60%, transparent);
  background: linear-gradient(
    100deg,
    var(--theme-bg-surface) 30%,
    color-mix(in srgb, var(--theme-bg-elevated) 70%, transparent) 50%,
    var(--theme-bg-surface) 70%
  );
  background-size: 220% 100%;
  animation: in-collections-shimmer 1.4s ease-in-out infinite;
}

@keyframes in-collections-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

.in-collections__more {
  margin-top: 0.85rem;
  color: var(--theme-text-muted);
  font-size: 0.78rem;
  font-weight: 700;
  text-align: center;
}

@media (prefers-reduced-motion: reduce) {
  .in-collections__skeleton { animation: none; }
}
</style>
