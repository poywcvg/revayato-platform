<script setup lang="ts">
import type { CollectionWritePayload } from '~/types'

definePageMeta({ middleware: 'auth' })

const { myCollections, loaded, refreshMine, createCollection } = useCollections()
const notifications = useNotifications()

const editorOpen = ref(false)
const creating = ref(false)
const createError = ref('')

await useAsyncData('my-collections', async () => {
  await refreshMine(true)
  return true
})

const totalTitles = computed(() => myCollections.value.reduce((sum, c) => sum + c.item_count, 0))
const publicCount = computed(() => myCollections.value.filter(c => c.visibility === 'public').length)

async function onCreate(payload: CollectionWritePayload) {
  creating.value = true
  createError.value = ''
  try {
    const created = await createCollection(payload)
    editorOpen.value = false
    notifications.success('کالکشن ساخته شد', `«${created.title}» آماده است.`)
    await navigateTo(`/collections/my/${created.slug}`)
  } catch (error) {
    createError.value = getAppError(error, 'ساخت کالکشن ممکن نشد.').reason || 'ساخت کالکشن ممکن نشد.'
  } finally {
    creating.value = false
  }
}

useSeoMeta({ title: 'کالکشن‌های من', description: 'فهرست‌های شخصی از فیلم‌ها و سریال‌ها را بساز، بچین و به اشتراک بگذار.' })
</script>

<template>
  <div class="cinema-page page-section pb-14 sm:pb-20">
    <header class="my-coll-head">
      <div class="min-w-0">
        <p class="text-xs font-black text-brand">فضای شخصی</p>
        <h1 class="mt-1 text-2xl font-black text-ink sm:text-3xl">کالکشن‌های من</h1>
        <p class="mt-1.5 text-sm leading-7 text-secondary">
          فیلم‌ها و سریال‌های محبوبت را در فهرست‌های دلخواه بچین و لینکشان را با دوستانت به اشتراک بگذار.
        </p>
      </div>
      <button type="button" class="ui-primary-button min-h-11 flex-none" @click="editorOpen = true">
        <CinematicIcon name="plus" class="size-4.5" />کالکشن جدید
      </button>
    </header>

    <div v-if="loaded && myCollections.length" class="my-coll-stats">
      <div class="my-coll-stat">
        <strong>{{ myCollections.length.toLocaleString('fa-IR') }}</strong>
        <span>کالکشن</span>
      </div>
      <div class="my-coll-stat">
        <strong>{{ totalTitles.toLocaleString('fa-IR') }}</strong>
        <span>عنوان</span>
      </div>
      <div class="my-coll-stat">
        <strong>{{ publicCount.toLocaleString('fa-IR') }}</strong>
        <span>عمومی</span>
      </div>
    </div>

    <div v-if="!loaded" class="grid place-items-center py-16">
      <LoadingSpinnerA />
    </div>

    <div v-else-if="!myCollections.length" class="mt-6">
      <EmptyState
        title="هنوز کالکشنی نساخته‌ای"
        description="اولین فهرستت را بساز؛ مثلاً «شاهکارهای سینما»، «برای یک شب بارانی» یا «لیست تماشای آخر هفته»."
        icon="layers"
      />
      <div class="mt-4 flex justify-center">
        <button type="button" class="ui-primary-button min-h-11" @click="editorOpen = true">
          <CinematicIcon name="plus" class="size-4.5" />ساخت اولین کالکشن
        </button>
      </div>
    </div>

    <div v-else class="my-coll-grid">
      <CollectionSummaryCard
        v-for="collection in myCollections"
        :key="collection.id"
        :collection="collection"
        :to="`/collections/my/${collection.slug}`"
      />
    </div>

    <CollectionEditorModal
      :open="editorOpen"
      mode="create"
      :pending="creating"
      :error="createError"
      @save="onCreate"
      @close="editorOpen = false"
    />
  </div>
</template>

<style scoped>
.my-coll-head {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: flex-start;
}
@media (min-width: 640px) {
  .my-coll-head { flex-direction: row; align-items: flex-end; justify-content: space-between; }
}

.my-coll-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.6rem;
  margin-top: 1.25rem;
  max-width: 26rem;
}
.my-coll-stat {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 70%, transparent);
  border-radius: 1rem;
  background: var(--theme-bg-surface);
  padding: 0.75rem;
  text-align: center;
}
.my-coll-stat strong { color: var(--theme-text-primary); font-size: 1.25rem; font-weight: 900; }
.my-coll-stat span { color: var(--theme-text-muted); font-size: 0.75rem; font-weight: 700; }

.my-coll-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 15rem), 1fr));
  gap: 1rem;
  margin-top: 1.5rem;
}
</style>
