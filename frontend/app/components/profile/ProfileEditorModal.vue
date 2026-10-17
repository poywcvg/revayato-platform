<script setup lang="ts">
// The profile editor used to expand inline inside the hero, which meant the
// page carried the weight of a whole form in its resting layout. As a dialog it
// only exists while it is being used. Pattern matches collection/EditorModal.
const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const authStore = useAuthStore()
const notifications = useNotifications()

const LANGUAGES = [
  { value: 'fa', label: 'فارسی' },
  { value: 'en', label: 'English' },
] as const

const BIO_LIMIT = 500
const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const AVATAR_MAX_BYTES = 5 * 1024 * 1024

const bio = ref('')
const language = ref<'fa' | 'en'>('fa')
const avatarFile = shallowRef<File | null>(null)
const avatarPreview = ref('')
const removeAvatar = ref(false)
const error = ref('')

const avatarInput = useTemplateRef<HTMLInputElement>('avatarInput')
const bioInput = useTemplateRef<HTMLTextAreaElement>('bioInput')

const avatarInitial = computed(() => (authStore.user?.username || 'ر').trim().charAt(0).toUpperCase())
const avatarSource = computed(() => {
  if (avatarPreview.value) return avatarPreview.value
  if (removeAvatar.value) return ''
  return authStore.user?.profile.avatar || ''
})

function clearPreview() {
  if (avatarPreview.value) URL.revokeObjectURL(avatarPreview.value)
  avatarPreview.value = ''
}

watch(() => props.open, async (open) => {
  if (!import.meta.client) return
  document.body.style.overflow = open ? 'hidden' : ''
  clearPreview()
  if (!open) return
  bio.value = authStore.user?.profile.bio || ''
  language.value = authStore.user?.profile.preferred_language === 'en' ? 'en' : 'fa'
  avatarFile.value = null
  removeAvatar.value = false
  error.value = ''
  await nextTick()
  bioInput.value?.focus()
}, { immediate: true })

onKeyStroke('Escape', () => {
  if (props.open && !authStore.pending) emit('close')
})

onBeforeUnmount(() => {
  clearPreview()
  if (import.meta.client) document.body.style.overflow = ''
})

function chooseAvatar() {
  avatarInput.value?.click()
}

function onAvatarSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!AVATAR_TYPES.includes(file.type)) {
    error.value = 'تصویر پروفایل باید JPEG، PNG یا WebP باشد.'
    return
  }
  if (file.size > AVATAR_MAX_BYTES) {
    error.value = 'حجم تصویر پروفایل باید کمتر از ۵ مگابایت باشد.'
    return
  }
  clearPreview()
  avatarFile.value = file
  avatarPreview.value = URL.createObjectURL(file)
  removeAvatar.value = false
  error.value = ''
}

function dropAvatar() {
  clearPreview()
  avatarFile.value = null
  removeAvatar.value = true
}

async function save() {
  error.value = ''
  const trimmed = bio.value.trim()
  if (trimmed.length > BIO_LIMIT) {
    error.value = `متن معرفی نباید بیشتر از ${BIO_LIMIT.toLocaleString('fa-IR')} نویسه باشد.`
    bioInput.value?.focus()
    return
  }
  try {
    if (removeAvatar.value && !avatarFile.value) {
      await authStore.updateProfile({ bio: trimmed, preferred_language: language.value, avatar: null })
    } else {
      const payload = new FormData()
      payload.append('bio', trimmed)
      payload.append('preferred_language', language.value)
      if (avatarFile.value) payload.append('avatar', avatarFile.value)
      await authStore.updateProfile(payload)
    }
    notifications.success('پروفایل به‌روز شد', 'تغییرات حساب همین حالا ذخیره شد.')
    emit('close')
  } catch (cause) {
    error.value = getAppError(cause, 'ذخیره تغییرات پروفایل ممکن نشد.').reason
      || 'ذخیره تغییرات پروفایل ممکن نشد.'
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-200"
      enter-from-class="opacity-0"
      leave-active-class="transition duration-150"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="fixed inset-0 z-[110] flex cursor-pointer items-end justify-center bg-[var(--theme-overlay-backdrop)] pt-4 sm:grid sm:place-items-center sm:p-4"
        role="presentation"
        @click.self="!authStore.pending && emit('close')"
      >
        <section
          role="dialog"
          aria-modal="true"
          aria-labelledby="profile-editor-title"
          class="max-h-[calc(100dvh-1rem)] w-[min(100%,calc(100dvw-1rem))] max-w-lg cursor-default overflow-y-auto rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] text-ink ring-1 ring-line sm:rounded-3xl sm:pb-0"
        >
          <header class="flex items-start justify-between gap-3 border-b border-line p-5 sm:p-6">
            <h2 id="profile-editor-title" class="text-lg font-black text-ink">ویرایش پروفایل</h2>
            <button
              type="button"
              class="grid size-10 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-elevated hover:text-ink"
              aria-label="بستن"
              @click="emit('close')"
            >
              <CinematicIcon name="x" class="size-5" />
            </button>
          </header>

          <form class="space-y-5 p-5 sm:p-6" @submit.prevent="save">
            <div class="flex items-center gap-4">
              <span class="pe-avatar">
                <img v-if="avatarSource" :src="avatarSource" alt="پیش‌نمایش تصویر پروفایل" class="size-full object-cover">
                <span v-else>{{ avatarInitial }}</span>
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap gap-2">
                  <button type="button" class="ui-secondary-button min-h-10 px-3 text-xs" @click="chooseAvatar">
                    <CinematicIcon name="edit" class="size-4" />انتخاب تصویر
                  </button>
                  <button v-if="avatarSource" type="button" class="ui-ghost-button min-h-10 px-3 text-xs" @click="dropAvatar">
                    حذف
                  </button>
                </div>
                <p class="mt-1.5 text-xs leading-5 text-muted">JPEG، PNG یا WebP تا ۵ مگابایت</p>
              </div>
              <input ref="avatarInput" type="file" accept="image/jpeg,image/png,image/webp" class="sr-only" @change="onAvatarSelected">
            </div>

            <div>
              <label for="profile-bio" class="text-xs font-bold text-secondary">درباره من</label>
              <textarea
                id="profile-bio"
                ref="bioInput"
                v-model="bio"
                rows="4"
                :maxlength="BIO_LIMIT"
                class="ui-field mt-2 resize-y px-3 py-3 text-sm leading-7"
                placeholder="از سلیقه سینمایی‌ات یا فیلم‌هایی که دوست داری بنویس…"
              />
              <div class="mt-1 flex items-center justify-between gap-3 text-[11px] text-muted">
                <span>در پروفایل عمومی تو دیده می‌شود.</span>
                <span class="font-latin tabular-nums">{{ bio.length.toLocaleString('fa-IR') }}/{{ BIO_LIMIT.toLocaleString('fa-IR') }}</span>
              </div>
            </div>

            <div>
              <span class="text-xs font-bold text-secondary">زبان ترجیحی رابط</span>
              <div class="mt-2 max-w-44">
                <UiSelect
                  v-model="language"
                  :options="LANGUAGES"
                  label="زبان ترجیحی رابط"
                  icon="globe"
                  compact
                />
              </div>
            </div>

            <div v-if="error" class="flex items-start gap-2 rounded-xl bg-red-500/10 p-3 text-xs leading-6 text-red-300 ring-1 ring-red-500/25" role="alert">
              <CinematicIcon name="info" class="mt-0.5 size-4 shrink-0" />{{ error }}
            </div>

            <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button type="button" class="ui-ghost-button min-h-11" :disabled="authStore.pending" @click="emit('close')">انصراف</button>
              <button type="submit" class="ui-primary-button min-h-11" :disabled="authStore.pending">
                <CinematicIcon :name="authStore.pending ? 'refresh' : 'check'" class="size-4.5" :class="authStore.pending && 'animate-spin'" />
                {{ authStore.pending ? 'در حال ذخیره…' : 'ذخیره تغییرات' }}
              </button>
            </div>
          </form>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.pe-avatar {
  display: grid;
  width: 4.5rem;
  height: 4.5rem;
  flex: none;
  place-items: center;
  overflow: hidden;
  border-radius: 1.25rem;
  background: linear-gradient(145deg, var(--theme-accent-primary), var(--theme-primary-700));
  color: var(--theme-on-accent);
  font-family: var(--font-latin-ui);
  font-size: 1.5rem;
  font-weight: 800;
}
</style>
