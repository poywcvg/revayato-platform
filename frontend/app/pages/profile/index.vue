<script setup lang="ts">
import type { CinematicIconName } from '~/types'

definePageMeta({ middleware: 'auth' })

const { catalog } = useCatalog()
const { watchlist, likes } = useLibrary()
const { continueWatching } = useWatchProgress()
const { stats: watchTimeStats } = useWatchTime()
const authStore = useAuthStore()
const notifications = useNotifications()

const editOpen = ref(false)
const bioDraft = ref('')
const languageDraft = ref('fa')
const avatarFile = shallowRef<File | null>(null)
const avatarPreview = ref('')
const removeAvatar = ref(false)
const formError = ref('')
const avatarInput = useTemplateRef<HTMLInputElement>('avatarInput')

const displayName = computed(() => authStore.user?.username || 'کاربر روایتو')
const avatarInitial = computed(() => displayName.value.trim().charAt(0).toUpperCase() || 'ر')
const avatarSource = computed(() => {
  if (avatarPreview.value) return avatarPreview.value
  if (removeAvatar.value) return ''
  return authStore.user?.profile.avatar || ''
})
const profileBio = computed(() => authStore.user?.profile.bio?.trim() || 'هنوز چیزی درباره خودت ننوشته‌ای.')
const isVerified = computed(() => Boolean(authStore.user?.is_verified || authStore.user?.profile.is_email_verified))
const memberSince = computed(() => {
  const value = authStore.user?.profile.created_at
  if (!value) return 'همین تازگی'
  try {
    return new Intl.DateTimeFormat('fa-IR', { year: 'numeric', month: 'long' }).format(new Date(value))
  } catch {
    return 'همین تازگی'
  }
})
const watchTimeLabel = computed(() => {
  const hours = watchTimeStats.value.hours
  const minutes = watchTimeStats.value.minutes
  if (hours <= 0 && minutes <= 0) return '۰ دقیقه'
  if (hours <= 0) return `${minutes.toLocaleString('fa-IR')} دقیقه`
  if (minutes <= 0) return `${hours.toLocaleString('fa-IR')} ساعت`
  return `${hours.toLocaleString('fa-IR')}س ${minutes.toLocaleString('fa-IR')}د`
})
const profileCompletion = computed(() => {
  let value = 35
  if (authStore.user?.profile.avatar) value += 25
  if (authStore.user?.profile.bio?.trim()) value += 25
  if (isVerified.value) value += 15
  return Math.min(100, value)
})

const stats = computed<Array<{ label: string; value: string; icon: CinematicIconName; to: string }>>(() => [
  { label: 'زمان تماشا', value: watchTimeLabel.value, icon: 'clock', to: '#watch-time' },
  { label: 'لیست من', value: watchlist.value.length.toLocaleString('fa-IR'), icon: 'bookmark', to: '/watchlist' },
  { label: 'پسندیده‌ها', value: likes.value.length.toLocaleString('fa-IR'), icon: 'heart', to: '/profile/favorites' },
  { label: 'کامل دیده‌شده', value: watchTimeStats.value.titles_completed.toLocaleString('fa-IR'), icon: 'check', to: '#watch-time' },
])

const quickLinks: Array<{ label: string; description: string; icon: CinematicIconName; to: string }> = [
  { label: 'ادامه تماشا', description: 'برگشت به آخرین عنوان‌ها', icon: 'resume', to: '#continue' },
  { label: 'لیست من', description: 'عنوان‌های ذخیره‌شده', icon: 'bookmark', to: '/watchlist' },
  { label: 'پسندیده‌ها', description: 'انتخاب‌های موردعلاقه', icon: 'heart', to: '/profile/favorites' },
  { label: 'سلیقه و پیشنهادها', description: 'تنظیم پیشنهادهای شخصی', icon: 'sliders', to: '#personalization' },
]

const profileSections = [
  { label: 'نمای کلی', target: 'overview' },
  { label: 'ادامه تماشا', target: 'continue' },
  { label: 'آمار تماشا', target: 'watch-time' },
  { label: 'پیشنهادهای من', target: 'personalization' },
] as const
const sectionItems = profileSections.map(section => section.label)

function scrollToSection(index: number) {
  const section = profileSections[index]
  if (!section) return
  document.getElementById(section.target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const continueItems = computed(() => continueWatching.value.slice(0, 4))
const watchlistItems = computed(() => catalog.value.filter(item =>
  watchlist.value.some(entry => entry.content_type === item.type && entry.object_id === item.id),
).slice(0, 10))

function clearAvatarPreview() {
  if (avatarPreview.value) URL.revokeObjectURL(avatarPreview.value)
  avatarPreview.value = ''
}

function openEditor() {
  bioDraft.value = authStore.user?.profile.bio || ''
  languageDraft.value = authStore.user?.profile.preferred_language || 'fa'
  avatarFile.value = null
  removeAvatar.value = false
  formError.value = ''
  clearAvatarPreview()
  editOpen.value = true
}

function closeEditor() {
  editOpen.value = false
  formError.value = ''
  avatarFile.value = null
  removeAvatar.value = false
  clearAvatarPreview()
}

function chooseAvatar() {
  avatarInput.value?.click()
}

function onAvatarSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    formError.value = 'تصویر پروفایل باید JPEG، PNG یا WebP باشد.'
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    formError.value = 'حجم تصویر پروفایل باید کمتر از ۵ مگابایت باشد.'
    return
  }
  clearAvatarPreview()
  avatarFile.value = file
  avatarPreview.value = URL.createObjectURL(file)
  removeAvatar.value = false
  formError.value = ''
}

function clearAvatar() {
  clearAvatarPreview()
  avatarFile.value = null
  removeAvatar.value = true
}

async function saveProfile() {
  formError.value = ''
  const bio = bioDraft.value.trim()
  if (bio.length > 500) {
    formError.value = 'متن معرفی نباید بیشتر از ۵۰۰ نویسه باشد.'
    return
  }
  try {
    if (removeAvatar.value && !avatarFile.value) {
      await authStore.updateProfile({ bio, preferred_language: languageDraft.value, avatar: null })
    } else {
      const payload = new FormData()
      payload.append('bio', bio)
      payload.append('preferred_language', languageDraft.value)
      if (avatarFile.value) payload.append('avatar', avatarFile.value)
      await authStore.updateProfile(payload)
    }
    notifications.success('پروفایل به‌روز شد', 'تغییرات حساب همین حالا ذخیره شد.')
    closeEditor()
  } catch (error) {
    formError.value = getAppError(error, 'ذخیره تغییرات پروفایل ممکن نشد.').reason
  }
}

async function logout() {
  await authStore.logout()
  notifications.info('از حساب خارج شدی', 'نشست این دستگاه با امنیت بسته شد.')
  await navigateTo('/')
}

onBeforeUnmount(clearAvatarPreview)

const visibilityHydration = { rootMargin: '320px 0px' }
useSeoMeta({ title: 'پروفایل من', description: 'مدیریت پروفایل، ادامه تماشا، ساعت تماشا و فهرست شخصی.' })
</script>

<template>
  <div class="profile-page cinema-page pb-14 sm:pb-20">
    <section class="page-section pb-0 pt-3 sm:pt-6">
      <div class="profile-hero">
        <span class="profile-hero__glow profile-hero__glow--one" aria-hidden="true" />
        <span class="profile-hero__glow profile-hero__glow--two" aria-hidden="true" />

        <div class="profile-hero__top">
          <div class="profile-identity">
            <button type="button" class="profile-avatar" aria-label="ویرایش تصویر پروفایل" @click="openEditor">
              <img v-if="authStore.user?.profile.avatar" :src="authStore.user.profile.avatar" alt="" class="size-full object-cover">
              <span v-else>{{ avatarInitial }}</span>
              <span class="profile-avatar__edit" aria-hidden="true"><CinematicIcon name="edit" class="size-3.5" /></span>
            </button>

            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <p class="profile-kicker">فضای شخصی من</p>
                <span v-if="isVerified" class="profile-verified"><CinematicIcon name="shield-check" class="size-3.5" />تأییدشده</span>
              </div>
              <h1 class="profile-title font-latin" dir="ltr">{{ displayName }}</h1>
              <p class="profile-bio">{{ profileBio }}</p>
              <p class="profile-member"><CinematicIcon name="calendar" class="size-3.5" />عضو روایتو از {{ memberSince }}</p>
            </div>
          </div>

          <div class="profile-hero__actions">
            <button type="button" class="ui-primary-button" @click="openEditor">
              <CinematicIcon name="edit" class="size-4.5" />
              ویرایش پروفایل
            </button>
            <NuxtLink to="/watchlist" class="ui-secondary-button">
              <CinematicIcon name="bookmark" class="size-4.5" />
              لیست من
            </NuxtLink>
          </div>
        </div>

        <div class="profile-stats" aria-label="خلاصه فعالیت حساب">
          <NuxtLink v-for="stat in stats" :key="stat.label" :to="stat.to" class="profile-stat">
            <span class="profile-stat__icon"><CinematicIcon :name="stat.icon" class="size-4.5" /></span>
            <span class="min-w-0">
              <strong class="profile-stat__value">{{ stat.value }}</strong>
              <span class="profile-stat__label">{{ stat.label }}</span>
            </span>
          </NuxtLink>
        </div>

        <nav class="profile-anchor-nav soft-scrollbar" aria-label="بخش‌های پروفایل">
          <a href="#overview">نمای کلی</a>
          <a href="#continue">ادامه تماشا</a>
          <a href="#watch-time">آمار تماشا</a>
          <a href="#personalization">پیشنهادهای من</a>
        </nav>

        <Transition name="profile-editor">
          <form v-if="editOpen" class="profile-editor" @submit.prevent="saveProfile">
            <div class="profile-editor__head">
              <div>
                <p class="text-xs font-black text-brand">ویرایش حساب</p>
                <h2 class="mt-1 text-lg font-black text-ink">پروفایل را به سلیقهٔ خودت بساز</h2>
              </div>
              <button type="button" class="profile-editor__close" aria-label="بستن ویرایش پروفایل" @click="closeEditor">
                <CinematicIcon name="x" class="size-5" />
              </button>
            </div>

            <div class="profile-editor__body">
              <div class="profile-editor__avatar">
                <span class="profile-avatar profile-avatar--editor">
                  <img v-if="avatarSource" :src="avatarSource" alt="پیش‌نمایش تصویر پروفایل" class="size-full object-cover">
                  <span v-else>{{ avatarInitial }}</span>
                </span>
                <div class="flex flex-wrap gap-2">
                  <button type="button" class="ui-secondary-button min-h-11 px-3 text-xs" @click="chooseAvatar">
                    <CinematicIcon name="edit" class="size-4" />انتخاب تصویر
                  </button>
                  <button v-if="avatarSource" type="button" class="ui-ghost-button min-h-11 px-3 text-xs" @click="clearAvatar">حذف تصویر</button>
                </div>
                <input ref="avatarInput" type="file" accept="image/jpeg,image/png,image/webp" class="sr-only" @change="onAvatarSelected">
                <p class="text-[11px] leading-5 text-muted">JPEG، PNG یا WebP تا ۵ مگابایت</p>
              </div>

              <div class="min-w-0 flex-1">
                <label for="profile-bio" class="text-xs font-bold text-secondary">درباره من</label>
                <textarea id="profile-bio" v-model="bioDraft" rows="4" maxlength="500" class="ui-field mt-2 resize-y px-3 py-3 text-sm leading-7" placeholder="از سلیقه سینمایی‌ات یا فیلم‌هایی که دوست داری بنویس…" />
                <div class="mt-1 flex items-center justify-between gap-3 text-[10px] text-muted">
                  <span>این متن در پروفایل تو نمایش داده می‌شود.</span>
                  <span class="font-latin tabular-nums">{{ bioDraft.length.toLocaleString('fa-IR') }}/۵۰۰</span>
                </div>

                <div v-if="formError" class="mt-3 flex items-start gap-2 rounded-xl bg-red-500/10 p-3 text-xs leading-6 text-red-300 ring-1 ring-red-500/25" role="alert">
                  <CinematicIcon name="info" class="mt-0.5 size-4 shrink-0" />{{ formError }}
                </div>

                <div class="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                  <button type="button" class="ui-ghost-button min-h-11" :disabled="authStore.pending" @click="closeEditor">انصراف</button>
                  <button type="submit" class="ui-primary-button min-h-11" :disabled="authStore.pending">
                    <CinematicIcon :name="authStore.pending ? 'refresh' : 'check'" class="size-4.5" :class="authStore.pending && 'animate-spin'" />
                    {{ authStore.pending ? 'در حال ذخیره…' : 'ذخیره تغییرات' }}
                  </button>
                </div>
              </div>
            </div>
          </form>
        </Transition>
      </div>
    </section>

    <section id="overview" class="content-section scroll-under-header">
      <div class="profile-overview-grid">
        <div id="continue" class="scroll-under-header min-w-0">
          <SectionHeader
            title="ادامه تماشا"
            eyebrow="برگشت سریع"
            description="از همان لحظه‌ای که متوقف کردی ادامه بده."
            href="/movies"
            link-label="پیدا کردن عنوان"
            icon="resume"
          />
          <div v-if="continueItems.length" class="grid gap-3 sm:grid-cols-2">
            <ContinueWatchingCard v-for="item in continueItems" :key="`${item.type}-${item.id}`" :item="item" />
          </div>
          <EmptyState
            v-else
            title="هنوز چیزی در حال تماشا نیست"
            description="پخش یک فیلم یا سریال را شروع کن؛ ادامه‌اش از همین‌جا در دسترس می‌ماند."
            icon="resume"
            action-label="مرور فیلم‌ها"
            action-href="/movies"
          />
        </div>

        <aside class="profile-side" aria-label="میانبرهای حساب">
          <section class="profile-panel profile-panel--sections">
            <div class="profile-panel__head">
              <span class="profile-panel__icon"><CinematicIcon name="list-video" class="size-5" /></span>
              <div><h2>بخش‌های صفحه</h2><p>پرش سریع بین بخش‌ها</p></div>
            </div>
            <LineSidebar
              :items="sectionItems"
              aria-label="بخش‌های پروفایل"
              accent-color="var(--theme-accent-primary)"
              text-color="var(--theme-text-secondary)"
              marker-color="var(--theme-text-muted)"
              :proximity-radius="80"
              :max-shift="16"
              :marker-length="44"
              :item-gap="14"
              :font-size="0.8"
              :default-active="0"
              class="profile-sections-nav"
              @item-click="scrollToSection"
            />
          </section>

          <section class="profile-panel">
            <div class="profile-panel__head">
              <span class="profile-panel__icon"><CinematicIcon name="grid" class="size-5" /></span>
              <div><h2>دسترسی سریع</h2><p>همه چیز نزدیک دست تو</p></div>
            </div>
            <nav class="profile-quick-links">
              <NuxtLink v-for="item in quickLinks" :key="item.to" :to="item.to" class="profile-quick-link">
                <span class="profile-quick-link__icon"><CinematicIcon :name="item.icon" class="size-4.5" /></span>
                <span class="min-w-0 flex-1"><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
                <CinematicIcon name="arrow-left" class="size-4 shrink-0 text-disabled" />
              </NuxtLink>
            </nav>
          </section>

          <section class="profile-panel profile-panel--account">
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-xs font-black text-brand">وضعیت پروفایل</p>
                <p class="mt-1 text-2xl font-black text-ink tabular-nums">{{ profileCompletion.toLocaleString('fa-IR') }}٪</p>
              </div>
              <span class="profile-panel__icon"><CinematicIcon name="shield-check" class="size-5" /></span>
            </div>
            <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10" role="progressbar" :aria-valuenow="profileCompletion" aria-valuemin="0" aria-valuemax="100" aria-label="درصد تکمیل پروفایل">
              <span class="block h-full rounded-full bg-primary-500 transition-[width] duration-500" :style="{ width: `${profileCompletion}%` }" />
            </div>
            <p class="mt-3 break-all text-xs leading-6 text-muted" dir="ltr">{{ authStore.user?.email }}</p>
            <button type="button" class="ui-destructive-button mt-4 min-h-11 w-full text-xs" @click="logout">
              <CinematicIcon name="logout" class="size-4" />خروج امن از حساب
            </button>
          </section>
        </aside>
      </div>
    </section>

    <WatchTimeStory />

    <LazyMovieRow
      v-if="watchlistItems.length"
      :hydrate-on-visible="visibilityHydration"
      title="لیست من"
      eyebrow="برای تماشای بعدی"
      :items="watchlistItems"
      href="/watchlist"
    />

    <LazyPersonalizationSettings :hydrate-on-visible="visibilityHydration" />
  </div>
</template>

<style scoped>
.profile-hero {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--theme-border) 78%, transparent);
  border-radius: 1.35rem;
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--theme-accent-primary) 8%, var(--theme-bg-surface)), var(--theme-bg-surface) 45%, color-mix(in srgb, var(--theme-bg-elevated) 92%, black));
  padding: 1rem;
  box-shadow: 0 20px 55px rgb(0 0 0 / 18%);
}

.profile-hero__glow {
  position: absolute;
  z-index: -1;
  border-radius: 999px;
  filter: blur(4px);
  pointer-events: none;
}

.profile-hero__glow--one {
  inset: -7rem -5rem auto auto;
  width: 18rem;
  height: 18rem;
  background: radial-gradient(circle, rgb(var(--palette-sand-rgb) / 16%), transparent 68%);
}

.profile-hero__glow--two {
  inset: auto auto -9rem -6rem;
  width: 20rem;
  height: 20rem;
  background: radial-gradient(circle, rgb(var(--palette-mid-rgb) / 12%), transparent 68%);
}

.profile-hero__top {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.profile-identity {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: .85rem;
}

.profile-avatar {
  position: relative;
  display: grid;
  width: 4.75rem;
  height: 4.75rem;
  flex: none;
  place-items: center;
  overflow: hidden;
  border: 3px solid color-mix(in srgb, var(--theme-accent-primary) 35%, transparent);
  border-radius: 1.35rem;
  background: linear-gradient(145deg, var(--theme-accent-primary), var(--theme-primary-700));
  color: var(--theme-on-accent);
  font-family: var(--font-latin-ui);
  font-size: 1.45rem;
  font-weight: 800;
  box-shadow: 0 12px 32px rgb(0 0 0 / 28%);
}

button.profile-avatar { cursor: pointer; }
button.profile-avatar:focus-visible { outline: 3px solid var(--theme-focus-ring); outline-offset: 3px; }

.profile-avatar__edit {
  position: absolute;
  inset: auto auto .2rem .2rem;
  display: grid;
  width: 1.55rem;
  height: 1.55rem;
  place-items: center;
  border-radius: .55rem;
  background: rgb(5 8 7 / 82%);
  color: white;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 15%);
}

.profile-avatar--editor {
  width: 5.5rem;
  height: 5.5rem;
  border-radius: 1.5rem;
}

.profile-kicker {
  font-size: .7rem;
  font-weight: 800;
  color: var(--theme-accent-primary);
}

.profile-verified {
  display: inline-flex;
  align-items: center;
  gap: .25rem;
  border: 1px solid color-mix(in srgb, var(--theme-success) 30%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-success) 9%, transparent);
  padding: .2rem .5rem;
  color: var(--theme-success);
  font-size: .62rem;
  font-weight: 800;
}

.profile-title {
  margin-top: .25rem;
  overflow-wrap: anywhere;
  font-size: clamp(1.35rem, 7vw, 2.35rem);
  font-weight: 800;
  line-height: 1.15;
  color: var(--theme-text-primary);
}

.profile-bio {
  display: -webkit-box;
  overflow: hidden;
  margin-top: .45rem;
  max-width: 42rem;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  color: var(--theme-text-secondary);
  font-size: .78rem;
  line-height: 1.75;
}

.profile-member {
  display: flex;
  align-items: center;
  gap: .35rem;
  margin-top: .45rem;
  color: var(--theme-text-muted);
  font-size: .68rem;
}

.profile-hero__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .55rem;
}

.profile-hero__actions > * { min-height: 2.75rem; padding: .65rem .75rem; font-size: .75rem; }

.profile-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .5rem;
  margin-top: 1rem;
}

.profile-stat {
  display: flex;
  min-width: 0;
  min-height: 4rem;
  align-items: center;
  gap: .65rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 66%, transparent);
  border-radius: .95rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
  padding: .65rem;
  transition: border-color 160ms ease, background-color 160ms ease, transform 160ms ease;
}

.profile-stat:hover,
.profile-stat:focus-visible {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 38%, transparent);
  background: color-mix(in srgb, var(--theme-accent-primary) 9%, var(--theme-bg-elevated));
  transform: translateY(-1px);
}

.profile-stat__icon,
.profile-panel__icon,
.profile-quick-link__icon {
  display: grid;
  flex: none;
  place-items: center;
  border-radius: .75rem;
  background: color-mix(in srgb, var(--theme-accent-primary) 11%, transparent);
  color: var(--theme-accent-primary);
}

.profile-stat__icon { width: 2.15rem; height: 2.15rem; }
.profile-stat__value { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--theme-text-primary); font-size: .8rem; font-weight: 900; }
.profile-stat__label { display: block; margin-top: .2rem; color: var(--theme-text-muted); font-size: .63rem; }

.profile-anchor-nav {
  display: flex;
  overflow-x: auto;
  gap: .35rem;
  margin-top: 1rem;
  padding-top: .75rem;
  border-top: 1px solid color-mix(in srgb, var(--theme-border) 55%, transparent);
  scrollbar-width: none;
}

.profile-anchor-nav::-webkit-scrollbar { display: none; }
.profile-anchor-nav a { flex: none; border-radius: .75rem; padding: .55rem .75rem; color: var(--theme-text-muted); font-size: .7rem; font-weight: 700; transition: color 140ms ease, background-color 140ms ease; }
.profile-anchor-nav a:hover,
.profile-anchor-nav a:focus-visible { background: color-mix(in srgb, var(--theme-accent-primary) 10%, transparent); color: var(--theme-accent-primary); }

.profile-editor {
  margin-top: 1rem;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--theme-accent-primary) 24%, var(--theme-border));
  border-radius: 1rem;
  background: color-mix(in srgb, var(--theme-bg-surface) 95%, transparent);
}

.profile-editor__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1rem; border-bottom: 1px solid var(--theme-border); }
.profile-editor__close { display: grid; width: 2.75rem; height: 2.75rem; flex: none; place-items: center; border-radius: .75rem; color: var(--theme-text-muted); transition: color 140ms ease, background-color 140ms ease; }
.profile-editor__close:hover { background: var(--theme-bg-elevated); color: var(--theme-text-primary); }
.profile-editor__body { display: flex; flex-direction: column; gap: 1.25rem; padding: 1rem; }
.profile-editor__avatar { display: flex; flex-direction: column; align-items: flex-start; gap: .7rem; }

.profile-editor-enter-active,
.profile-editor-leave-active { transition: opacity 180ms ease, transform 200ms cubic-bezier(.22, 1, .36, 1); }
.profile-editor-enter-from,
.profile-editor-leave-to { opacity: 0; transform: translateY(-.4rem); }

.profile-overview-grid { display: grid; gap: 1rem; }
.profile-side { display: grid; align-content: start; gap: .75rem; }
.profile-panel { overflow: hidden; border: 1px solid color-mix(in srgb, var(--theme-border) 75%, transparent); border-radius: 1.1rem; background: var(--theme-bg-surface); padding: 1rem; }
.profile-panel__head { display: flex; align-items: center; gap: .7rem; }
.profile-panel__head h2 { color: var(--theme-text-primary); font-size: .92rem; font-weight: 900; }
.profile-panel__head p { margin-top: .15rem; color: var(--theme-text-muted); font-size: .65rem; }
.profile-sections-nav { margin-top: .4rem; }
.profile-panel__icon { width: 2.5rem; height: 2.5rem; }
.profile-quick-links { display: grid; gap: .3rem; margin-top: .8rem; }
.profile-quick-link { display: flex; min-height: 3.5rem; align-items: center; gap: .65rem; border-radius: .85rem; padding: .45rem .5rem; transition: background-color 140ms ease; }
.profile-quick-link:hover,
.profile-quick-link:focus-visible { background: var(--theme-bg-elevated); }
.profile-quick-link__icon { width: 2.15rem; height: 2.15rem; }
.profile-quick-link strong { display: block; color: var(--theme-text-primary); font-size: .76rem; font-weight: 800; }
.profile-quick-link small { display: block; margin-top: .15rem; color: var(--theme-text-muted); font-size: .62rem; }
.profile-panel--account { background: linear-gradient(145deg, color-mix(in srgb, var(--theme-accent-primary) 6%, var(--theme-bg-surface)), var(--theme-bg-surface)); }

@media (min-width: 640px) {
  .profile-hero { border-radius: 1.75rem; padding: 1.5rem; }
  .profile-avatar { width: 5.75rem; height: 5.75rem; border-radius: 1.6rem; font-size: 1.8rem; }
  .profile-hero__actions { display: flex; }
  .profile-stats { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .7rem; }
  .profile-stat { min-height: 4.5rem; padding: .75rem; }
  .profile-editor__head,
  .profile-editor__body { padding: 1.25rem; }
  .profile-editor__body { flex-direction: row; }
  .profile-editor__avatar { width: 12rem; flex: none; }
}

@media (min-width: 1024px) {
  .profile-hero { padding: 1.75rem; }
  .profile-hero__top { flex-direction: row; align-items: flex-start; justify-content: space-between; gap: 2rem; }
  .profile-hero__actions { flex: none; }
  .profile-overview-grid { grid-template-columns: minmax(0, 2fr) minmax(17rem, .8fr); gap: 1.25rem; }
  .profile-stat__value { font-size: .9rem; }
}

@media (max-width: 359px) {
  .profile-hero { padding: .8rem; }
  .profile-avatar { width: 4.1rem; height: 4.1rem; }
  .profile-bio { -webkit-line-clamp: 1; }
  .profile-stat { gap: .45rem; padding: .5rem; }
  .profile-stat__icon { width: 1.9rem; height: 1.9rem; }
}

@media (prefers-reduced-motion: reduce) {
  .profile-editor-enter-active,
  .profile-editor-leave-active,
  .profile-stat { transition: none; }
}
</style>
