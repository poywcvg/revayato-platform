<script setup lang="ts">
import type { CollectionItem, CollectionWritePayload, UserCollection } from '~/types'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const slug = computed(() => String(route.params.slug || ''))
const { fetchMyCollection, updateCollection, deleteCollection, removeItem, refreshMine } = useCollections()
const notifications = useNotifications()

const { data: collection, error, refresh } = await useAsyncData<UserCollection>(
  () => `my-collection-${slug.value}`,
  () => fetchMyCollection(slug.value),
)

if (error.value) {
  throw createError({ statusCode: 404, statusMessage: 'کالکشن پیدا نشد.', fatal: true })
}

const editorOpen = ref(false)
const savingEdit = ref(false)
const editError = ref('')
const deleteOpen = ref(false)
const deleting = ref(false)

async function onEdit(payload: CollectionWritePayload) {
  savingEdit.value = true
  editError.value = ''
  try {
    const updated = await updateCollection(slug.value, payload)
    if (collection.value) collection.value = { ...collection.value, ...updated }
    editorOpen.value = false
    notifications.success('ذخیره شد', 'تغییرات کالکشن اعمال شد.')
    if (updated.slug !== slug.value) await navigateTo(`/collections/my/${updated.slug}`, { replace: true })
  } catch (err) {
    editError.value = getAppError(err, 'ذخیره تغییرات ممکن نشد.').reason || 'ذخیره تغییرات ممکن نشد.'
  } finally {
    savingEdit.value = false
  }
}

async function onRemove(item: CollectionItem) {
  if (!collection.value) return
  const previous = collection.value.items ?? []
  collection.value = {
    ...collection.value,
    items: previous.filter(i => !(i.content_type === item.content_type && i.id === item.id)),
    item_count: Math.max(0, collection.value.item_count - 1),
  }
  try {
    await removeItem(slug.value, item.content_type, item.id)
  } catch {
    if (collection.value) collection.value = { ...collection.value, items: previous, item_count: previous.length }
    notifications.error('حذف نشد', 'دوباره تلاش کن.')
  }
}

async function confirmDelete() {
  deleting.value = true
  try {
    await deleteCollection(slug.value)
    notifications.success('کالکشن حذف شد', 'فهرست برای همیشه پاک شد.')
    void refreshMine(true)
    await navigateTo('/collections/my')
  } catch (err) {
    notifications.error('حذف نشد', getAppError(err).reason || 'دوباره تلاش کن.')
    deleting.value = false
    deleteOpen.value = false
  }
}

useSeoMeta({
  title: () => (collection.value ? `${collection.value.title} — کالکشن من` : 'کالکشن'),
  robots: 'noindex',
})
</script>

<template>
  <div class="cinema-page page-section pb-14 sm:pb-20">
    <div class="mb-4 flex items-center justify-between gap-3">
      <NuxtLink to="/collections/my" class="inline-flex items-center gap-1.5 text-sm font-bold text-secondary transition hover:text-ink">
        <CinematicIcon name="arrow-right" class="size-4" />کالکشن‌های من
      </NuxtLink>
      <button
        v-if="collection"
        type="button"
        class="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold text-red-300 transition hover:bg-red-500/10"
        @click="deleteOpen = true"
      >
        <CinematicIcon name="trash" class="size-4" />حذف کالکشن
      </button>
    </div>

    <CollectionDetailView
      v-if="collection"
      :collection="collection"
      can-manage
      @edit="editorOpen = true"
      @remove="onRemove"
    />

    <CollectionEditorModal
      :open="editorOpen"
      mode="edit"
      :collection="collection"
      :pending="savingEdit"
      :error="editError"
      @save="onEdit"
      @close="editorOpen = false"
    />

    <Teleport to="body">
      <Transition enter-active-class="transition duration-200" enter-from-class="opacity-0" leave-active-class="transition duration-150" leave-to-class="opacity-0">
        <div
          v-if="deleteOpen"
          class="fixed inset-0 z-[110] grid cursor-pointer place-items-center bg-[var(--theme-overlay-backdrop)] p-4"
          role="presentation"
          @click.self="deleteOpen = false"
        >
          <section role="dialog" aria-modal="true" class="w-full max-w-sm cursor-default rounded-3xl bg-surface p-5 text-ink ring-1 ring-line sm:p-6">
            <span class="grid size-12 place-items-center rounded-2xl bg-red-500/12 text-red-300 ring-1 ring-red-500/20"><CinematicIcon name="trash" class="size-6" /></span>
            <h2 class="mt-4 text-lg font-black text-ink">حذف «{{ collection?.title }}»؟</h2>
            <p class="mt-1.5 text-sm leading-7 text-secondary">این کالکشن و همهٔ عنوان‌های داخلش برای همیشه پاک می‌شوند. عنوان‌ها از کاتالوگ حذف نمی‌شوند.</p>
            <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button type="button" class="ui-ghost-button min-h-11" :disabled="deleting" @click="deleteOpen = false">انصراف</button>
              <button type="button" class="ui-destructive-button min-h-11" :disabled="deleting" @click="confirmDelete">
                <CinematicIcon :name="deleting ? 'refresh' : 'trash'" class="size-4.5" :class="deleting && 'animate-spin'" />
                {{ deleting ? 'در حال حذف…' : 'حذف کن' }}
              </button>
            </div>
          </section>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
