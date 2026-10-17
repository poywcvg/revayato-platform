<script setup lang="ts">
import type { CollectionVisibility, CollectionWritePayload, UserCollection } from '~/types'

const props = withDefaults(defineProps<{
  open: boolean
  mode?: 'create' | 'edit'
  collection?: UserCollection | null
  pending?: boolean
  error?: string
  confirmLabel?: string
}>(), {
  mode: 'create',
  collection: null,
  pending: false,
  error: '',
  confirmLabel: '',
})

const emit = defineEmits<{ save: [CollectionWritePayload]; close: [] }>()

const ACCENTS = ['#7c5cff', '#ff5c8a', '#2dd4bf', '#f59e0b', '#38bdf8', '#a3e635', '#fb7185', '#c084fc']
const VISIBILITIES: CollectionVisibility[] = ['public', 'unlisted', 'private']

const title = ref('')
const description = ref('')
const visibility = ref<CollectionVisibility>('public')
const accent = ref(ACCENTS[0]!)
const localError = ref('')

const dialog = useTemplateRef<HTMLElement>('dialog')
const titleInput = useTemplateRef<HTMLInputElement>('titleInput')

const heading = computed(() => (props.mode === 'edit' ? 'ویرایش کالکشن' : 'کالکشن تازه'))
const submitLabel = computed(() => props.confirmLabel || (props.mode === 'edit' ? 'ذخیره تغییرات' : 'بساز'))

watch(() => props.open, async (open) => {
  if (!import.meta.client) return
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) {
    title.value = props.collection?.title ?? ''
    description.value = props.collection?.description ?? ''
    visibility.value = props.collection?.visibility ?? 'public'
    accent.value = props.collection?.accent ?? ACCENTS[0]!
    localError.value = ''
    await nextTick()
    titleInput.value?.focus()
  }
}, { immediate: true })

onKeyStroke('Escape', () => { if (props.open) emit('close') })
onBeforeUnmount(() => { if (import.meta.client) document.body.style.overflow = '' })

function submit() {
  const trimmed = title.value.trim()
  if (!trimmed) {
    localError.value = 'عنوان کالکشن را بنویس.'
    titleInput.value?.focus()
    return
  }
  localError.value = ''
  emit('save', {
    title: trimmed,
    description: description.value.trim(),
    visibility: visibility.value,
    accent: accent.value,
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition enter-active-class="transition duration-200" enter-from-class="opacity-0" leave-active-class="transition duration-150" leave-to-class="opacity-0">
      <div
        v-if="open"
        class="fixed inset-0 z-[110] flex cursor-pointer items-end justify-center bg-[var(--theme-overlay-backdrop)] pt-4 sm:grid sm:place-items-center sm:p-4"
        role="presentation"
        @click.self="emit('close')"
      >
        <section
          ref="dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="coll-editor-title"
          class="max-h-[calc(100dvh-1rem)] w-[min(100%,calc(100dvw-1rem))] max-w-lg cursor-default overflow-y-auto rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] text-ink ring-1 ring-line sm:rounded-3xl sm:pb-0"
        >
          <header class="flex items-start justify-between gap-3 border-b border-line p-5 sm:p-6">
            <div>
              <p class="text-xs font-black text-brand">{{ heading }}</p>
              <h2 id="coll-editor-title" class="mt-1 text-lg font-black text-ink">یک فهرست به سلیقهٔ خودت</h2>
            </div>
            <button type="button" class="grid size-10 place-items-center rounded-xl text-muted transition hover:bg-elevated hover:text-ink" aria-label="بستن" @click="emit('close')">
              <CinematicIcon name="x" class="size-5" />
            </button>
          </header>

          <form class="space-y-5 p-5 sm:p-6" @submit.prevent="submit">
            <div>
              <label for="coll-title" class="text-xs font-bold text-secondary">عنوان</label>
              <input
                id="coll-title"
                ref="titleInput"
                v-model="title"
                type="text"
                maxlength="120"
                class="ui-field mt-2 px-3 py-2.5 text-sm"
                placeholder="مثلاً: شب‌های نوآر، بهترین‌های نولان…"
              >
            </div>

            <div>
              <label for="coll-desc" class="text-xs font-bold text-secondary">توضیح <span class="text-muted">(اختیاری)</span></label>
              <textarea
                id="coll-desc"
                v-model="description"
                rows="3"
                maxlength="2000"
                class="ui-field mt-2 resize-y px-3 py-2.5 text-sm leading-7"
                placeholder="این فهرست دربارهٔ چیست؟"
              />
            </div>

            <div>
              <span class="text-xs font-bold text-secondary">رنگ کالکشن</span>
              <div class="mt-2 flex flex-wrap gap-2">
                <button
                  v-for="swatch in ACCENTS"
                  :key="swatch"
                  type="button"
                  class="size-8 rounded-xl ring-2 ring-offset-2 ring-offset-[var(--theme-bg-surface)] transition"
                  :class="accent === swatch ? 'ring-white/80 scale-110' : 'ring-transparent'"
                  :style="{ background: swatch }"
                  :aria-label="`رنگ ${swatch}`"
                  :aria-pressed="accent === swatch"
                  @click="accent = swatch"
                />
              </div>
            </div>

            <div>
              <span class="text-xs font-bold text-secondary">چه کسی می‌بیند؟</span>
              <div class="mt-2 grid gap-2">
                <button
                  v-for="option in VISIBILITIES"
                  :key="option"
                  type="button"
                  class="flex items-center gap-3 rounded-2xl border p-3 text-right transition"
                  :class="visibility === option ? 'border-primary-400/60 bg-primary-500/10' : 'border-line bg-elevated/40 hover:border-primary-400/30'"
                  @click="visibility = option"
                >
                  <span
                    class="grid size-9 flex-none place-items-center rounded-xl"
                    :class="visibility === option ? 'bg-primary-500/20 text-brand' : 'bg-white/5 text-muted'"
                  >
                    <CinematicIcon :name="COLLECTION_VISIBILITY[option].icon" class="size-4.5" />
                  </span>
                  <span class="min-w-0 flex-1">
                    <strong class="block text-sm font-black text-ink">{{ COLLECTION_VISIBILITY[option].label }}</strong>
                    <small class="block text-xs leading-5 text-muted">{{ COLLECTION_VISIBILITY[option].hint }}</small>
                  </span>
                  <CinematicIcon v-if="visibility === option" name="check-circle" class="size-5 flex-none text-brand" filled />
                </button>
              </div>
            </div>

            <div v-if="localError || error" class="flex items-start gap-2 rounded-xl bg-red-500/10 p-3 text-xs leading-6 text-red-300 ring-1 ring-red-500/25" role="alert">
              <CinematicIcon name="info" class="mt-0.5 size-4 shrink-0" />{{ localError || error }}
            </div>

            <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button type="button" class="ui-ghost-button min-h-11" :disabled="pending" @click="emit('close')">انصراف</button>
              <button type="submit" class="ui-primary-button min-h-11" :disabled="pending">
                <CinematicIcon :name="pending ? 'refresh' : 'check'" class="size-4.5" :class="pending && 'animate-spin'" />
                {{ pending ? 'در حال ذخیره…' : submitLabel }}
              </button>
            </div>
          </form>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
