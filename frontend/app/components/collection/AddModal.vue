<script setup lang="ts">
import type { CollectionPickRow, CollectionVisibility, CollectionWritePayload, ContentType } from '~/types'

const props = defineProps<{
  open: boolean
  contentType: ContentType
  objectId: number
  title: string
}>()

const emit = defineEmits<{ close: [] }>()

const { containing, addItem, removeItem, createCollection, refreshMine } = useCollections()
const notifications = useNotifications()

const rows = ref<CollectionPickRow[]>([])
const loading = ref(false)
const loadError = ref('')
const busy = reactive<Record<string, boolean>>({})
const editorOpen = ref(false)
const creating = ref(false)
const createError = ref('')

watch(() => props.open, async (open) => {
  if (!import.meta.client) return
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) await load()
}, { immediate: true })

onKeyStroke('Escape', () => { if (props.open && !editorOpen.value) emit('close') })
onBeforeUnmount(() => { if (import.meta.client) document.body.style.overflow = '' })

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    rows.value = await containing(props.contentType, props.objectId)
  } catch {
    loadError.value = 'فهرست کالکشن‌ها بارگذاری نشد.'
  } finally {
    loading.value = false
  }
}

async function toggle(row: CollectionPickRow) {
  if (busy[row.slug]) return
  busy[row.slug] = true
  const wasIn = row.contains
  try {
    const result = wasIn
      ? await removeItem(row.slug, props.contentType, props.objectId)
      : await addItem(row.slug, props.contentType, props.objectId)
    row.contains = wasIn ? false : true
    row.item_count = result.item_count
    notifications.success(
      wasIn ? 'از کالکشن حذف شد' : 'به کالکشن اضافه شد',
      `«${props.title}» ${wasIn ? 'از' : 'به'} «${row.title}»`,
    )
  } catch {
    notifications.error('انجام نشد', 'دوباره تلاش کن.')
  } finally {
    busy[row.slug] = false
  }
}

async function createAndAdd(payload: CollectionWritePayload) {
  creating.value = true
  createError.value = ''
  try {
    const created = await createCollection(payload)
    const result = await addItem(created.slug, props.contentType, props.objectId)
    rows.value = [
      { id: created.id, slug: created.slug, title: created.title, visibility: created.visibility, accent: created.accent, item_count: result.item_count, contains: true },
      ...rows.value,
    ]
    editorOpen.value = false
    notifications.success('کالکشن ساخته شد', `«${props.title}» به «${created.title}» اضافه شد.`)
    void refreshMine(true)
  } catch (error) {
    createError.value = getAppError(error, 'ساخت کالکشن ممکن نشد.').reason || 'ساخت کالکشن ممکن نشد.'
  } finally {
    creating.value = false
  }
}

function visLabel(v: CollectionVisibility) {
  return COLLECTION_VISIBILITY[v]?.label ?? ''
}
</script>

<template>
  <Teleport to="body">
    <Transition enter-active-class="transition duration-200" enter-from-class="opacity-0" leave-active-class="transition duration-150" leave-to-class="opacity-0">
      <div
        v-if="open"
        class="fixed inset-0 z-[105] flex cursor-pointer items-end justify-center bg-[var(--theme-overlay-backdrop)] pt-4 sm:grid sm:place-items-center sm:p-4"
        role="presentation"
        @click.self="emit('close')"
      >
        <section
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-coll-title"
          class="flex max-h-[calc(100dvh-1rem)] w-[min(100%,calc(100dvw-1rem))] max-w-md cursor-default flex-col overflow-hidden rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] text-ink ring-1 ring-line sm:rounded-3xl sm:pb-0"
        >
          <header class="flex items-start justify-between gap-3 border-b border-line p-5">
            <div class="min-w-0">
              <p class="text-xs font-black text-brand">افزودن به کالکشن</p>
              <h2 id="add-coll-title" class="mt-1 truncate text-base font-black text-ink">{{ title }}</h2>
            </div>
            <button type="button" class="grid size-10 flex-none place-items-center rounded-xl text-muted transition hover:bg-elevated hover:text-ink" aria-label="بستن" @click="emit('close')">
              <CinematicIcon name="x" class="size-5" />
            </button>
          </header>

          <div class="min-h-0 flex-1 overflow-y-auto p-3">
            <button
              type="button"
              class="flex w-full items-center gap-3 rounded-2xl border border-dashed border-primary-400/40 bg-primary-500/[.06] p-3 text-right transition hover:bg-primary-500/10"
              @click="editorOpen = true"
            >
              <span class="grid size-11 flex-none place-items-center rounded-xl bg-primary-500/15 text-brand">
                <CinematicIcon name="plus" class="size-5" />
              </span>
              <span class="min-w-0 flex-1">
                <strong class="block text-sm font-black text-ink">کالکشن جدید</strong>
                <small class="block text-xs text-muted">یک فهرست تازه بساز و همین عنوان را داخلش بگذار</small>
              </span>
            </button>

            <div v-if="loading" class="grid place-items-center py-10">
              <LoadingSpinnerA size="small" />
            </div>
            <p v-else-if="loadError" class="py-8 text-center text-sm text-muted">{{ loadError }}</p>
            <p v-else-if="!rows.length" class="px-2 py-8 text-center text-sm leading-7 text-muted">
              هنوز کالکشنی نساخته‌ای. با دکمهٔ بالا اولین فهرستت را بساز.
            </p>
            <ul v-else class="mt-2 space-y-1">
              <li v-for="row in rows" :key="row.slug">
                <button
                  type="button"
                  class="flex w-full items-center gap-3 rounded-2xl p-2.5 text-right transition hover:bg-elevated"
                  :disabled="busy[row.slug]"
                  @click="toggle(row)"
                >
                  <span class="size-11 flex-none rounded-xl" :style="{ background: row.accent }" aria-hidden="true" />
                  <span class="min-w-0 flex-1">
                    <strong class="block truncate text-sm font-bold text-ink">{{ row.title }}</strong>
                    <small class="block text-xs text-muted">{{ row.item_count.toLocaleString('fa-IR') }} عنوان · {{ visLabel(row.visibility) }}</small>
                  </span>
                  <span
                    class="grid size-7 flex-none place-items-center rounded-full border transition"
                    :class="row.contains ? 'border-transparent bg-primary-500 text-on-brand' : 'border-line text-muted'"
                  >
                    <CinematicIcon v-if="busy[row.slug]" name="refresh" class="size-4 animate-spin" />
                    <CinematicIcon v-else :name="row.contains ? 'check' : 'plus'" class="size-4" />
                  </span>
                </button>
              </li>
            </ul>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>

  <CollectionEditorModal
    :open="editorOpen"
    mode="create"
    :pending="creating"
    :error="createError"
    confirm-label="بساز و اضافه کن"
    @save="createAndAdd"
    @close="editorOpen = false"
  />
</template>
