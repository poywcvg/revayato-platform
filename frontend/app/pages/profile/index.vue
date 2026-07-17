<script setup lang="ts">
import type { CinematicIconName } from '~/types'

definePageMeta({ middleware: 'auth' })

const { catalog } = useCatalog()
const { watchlistIds, likedIds } = useLibrary()
const authStore = useAuthStore()
const notifications = useNotifications()
const displayName = computed(() => authStore.user?.username || 'کاربر سینما')
const avatarInitial = computed(() => displayName.value.trim().charAt(0).toUpperCase() || 'س')
const memberSince = computed(() => {
  const value = authStore.user?.profile.created_at
  return value ? new Intl.DateTimeFormat('fa-IR', { year: 'numeric', month: 'long' }).format(new Date(value)) : 'تازه‌وارد'
})

async function logout() {
  await authStore.logout()
  notifications.info('از حساب خارج شدی', 'نشست این دستگاه با امنیت بسته شد.')
  await navigateTo('/')
}
const continueWatching = computed(() => catalog.value.filter(item => item.progress_percent > 0))
const watchlist = computed(() => catalog.value.filter(item => watchlistIds.value.includes(item.id)).slice(0, 6))
const liked = computed(() => catalog.value.filter(item => likedIds.value.includes(item.id)))
const profileStats = computed<Array<{ label: string; value: number; icon: CinematicIconName }>>(() => [
  { label: 'در لیست من', value: watchlistIds.value.length, icon: 'bookmark' },
  { label: 'پسندیده‌ها', value: liked.value.length, icon: 'heart' },
  { label: 'در حال تماشا', value: continueWatching.value.length, icon: 'resume' },
  { label: 'امتیاز ثبت‌شده', value: 3, icon: 'star' },
])
const socialFeatures: Array<{ title: string; text: string; icon: CinematicIconName }> = [
  { title: 'نظرهای من', text: 'مرور و مدیریت نظرهایی که بعداً ثبت می‌کنید.', icon: 'comments' },
  { title: 'دوستان سینمایی', text: 'دنبال کردن کاربران و دیدن انتخاب‌های آن‌ها.', icon: 'users' },
  { title: 'پیشنهاد هوشمند', text: 'پیشنهاد بر پایه رفتار تماشا و امتیازهای شما.', icon: 'ai' },
]
const visibilityHydration = { rootMargin: '320px 0px' }
useSeoMeta({ title: 'پروفایل من', description: 'پروفایل، ادامه تماشا و لیست شخصی.' })
</script>

<template>
  <div class="pb-12">
    <section class="relative isolate overflow-hidden bg-gradient-to-bl from-wine via-canvas-soft to-canvas text-ink ring-1 ring-line">
      <div class="page-shell py-9 sm:py-12">
        <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex items-center gap-4"><span class="grid h-20 w-20 shrink-0 place-items-center overflow-hidden rounded-3xl bg-gradient-to-br from-primary-400 to-primary-700 text-2xl font-black shadow-xl ring-4 ring-white/10"><img v-if="authStore.user?.profile.avatar" :src="authStore.user.profile.avatar" alt="" class="size-full object-cover"><template v-else>{{ avatarInitial }}</template></span><div><p class="text-xs font-black text-primary-300">پروفایل من</p><h1 class="mt-1 text-2xl font-black sm:text-3xl">{{ displayName }}</h1><p class="mt-1 text-sm text-slate-400">عضو از {{ memberSince }}</p></div></div>
          <button type="button" class="ui-destructive-button w-fit" @click="logout"><CinematicIcon name="logout" class="size-5" />خروج از حساب</button>
        </div>
        <div class="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4"><div v-for="stat in profileStats" :key="stat.label" class="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10"><CinematicIcon :name="stat.icon" class="size-6 text-primary-400" :filled="['bookmark', 'heart', 'star'].includes(stat.icon)" /><p class="mt-3 text-2xl font-black">{{ stat.value }}</p><p class="mt-1 text-xs text-slate-400">{{ stat.label }}</p></div></div>
      </div>
    </section>

    <LazyPersonalizationSettings :hydrate-on-visible="visibilityHydration" />

    <section id="continue" class="content-section scroll-mt-24">
      <SectionHeader title="ادامه تماشا" eyebrow="فعالیت اخیر" />
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <NuxtLink v-for="item in continueWatching" :key="item.id" :to="{ path: `/watch/${item.slug}`, query: { type: item.type } }" class="cinematic-card group overflow-hidden rounded-2xl transition hover:-translate-y-0.5"><div class="relative aspect-video overflow-hidden bg-canvas-soft"><NuxtImg :src="item.backdrop_url" :alt="item.title" class="h-full w-full object-cover transition-transform group-hover:scale-105" loading="lazy" decoding="async" fetchpriority="low" /><div class="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" /><span class="absolute inset-0 m-auto grid size-10 place-items-center rounded-full bg-primary-500 text-night-950"><CinematicIcon name="resume" class="size-5" /></span><div class="absolute inset-x-0 bottom-0 h-1.5 bg-white/20"><div class="h-full bg-primary-500" :style="{ width: `${item.progress_percent}%` }" /></div></div><div class="p-4"><h3 class="font-black text-ink">{{ item.title }}</h3><p class="mt-1 text-xs text-muted">{{ item.progress_percent }}٪ تماشا شده</p></div></NuxtLink>
      </div>
    </section>

    <LazyMovieRow v-if="watchlist.length" :hydrate-on-visible="visibilityHydration" title="لیست من" eyebrow="برای بعد ذخیره کرده‌اید" :items="watchlist" href="/watchlist" />

    <section class="content-section render-later">
      <SectionHeader title="فضای اجتماعی" eyebrow="قابلیت‌های آینده" description="به‌زودی می‌توانی نظرهایت را مدیریت کنی، دوستانت را دنبال کنی و انتخاب‌هایشان را ببینی." />
      <div class="grid gap-4 md:grid-cols-3"><div v-for="feature in socialFeatures" :key="feature.title" class="ui-surface border-dashed p-5"><span class="grid size-10 place-items-center rounded-xl bg-elevated text-muted ring-1 ring-line"><CinematicIcon :name="feature.icon" class="size-5" /></span><h3 class="mt-4 font-black text-ink">{{ feature.title }}</h3><p class="mt-1 text-sm leading-6 text-muted">{{ feature.text }}</p><span class="mt-4 inline-flex rounded-lg bg-elevated px-2.5 py-1 text-[10px] font-black text-muted ring-1 ring-line">به‌زودی</span></div></div>
    </section>
  </div>
</template>
