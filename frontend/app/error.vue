<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()
const status = computed(() => Number(props.error.statusCode) || 500)
const content = computed(() => {
  if (status.value === 404) return { title: 'این صفحه پیدا نشد', message: 'ممکن است آدرس تغییر کرده باشد یا این محتوا دیگر در دسترس نباشد.', hint: 'به خانه برگرد یا از جستجو برای پیدا کردن فیلم استفاده کن.', icon: 'search' as const }
  if (status.value === 401) return { title: 'اول وارد حسابت شو', message: 'برای دیدن این صفحه باید وارد حساب کاربری باشی.', hint: 'پس از ورود دوباره به همین بخش برمی‌گردی.', icon: 'lock' as const }
  if (status.value === 403) return { title: 'دسترسی به این بخش ممکن نیست', message: 'حساب تو اجازه دیدن این صفحه را ندارد.', hint: 'اگر فکر می‌کنی اشتباهی رخ داده، با پشتیبانی تماس بگیر.', icon: 'shield-alert' as const }
  return { title: 'این صفحه درست باز نشد', message: 'یک مشکل موقت پیش آمده و درخواست تو کامل نشده است.', hint: 'صفحه را دوباره باز کن؛ اگر مشکل ماند، کمی بعد تلاش کن.', icon: 'alert-triangle' as const }
})

function goHome() {
  clearError({ redirect: '/' })
}

function retry() {
  if (import.meta.client) window.location.reload()
}

useSeoMeta({ title: () => content.value.title })
</script>

<template>
  <div class="cinematic-app grid min-h-dvh place-items-center bg-canvas px-4 py-10 text-ink">
    <main class="w-full max-w-xl rounded-[2rem] border border-line bg-surface p-6 text-center shadow-2xl shadow-black/40 sm:p-10">
      <AppLogo :compact-on-mobile="false" class="mx-auto w-fit" />
      <span class="mx-auto mt-8 grid size-16 place-items-center rounded-2xl bg-primary-500/10 text-primary-300 ring-1 ring-primary-500/20"><CinematicIcon :name="content.icon" class="size-8" /></span>
      <p class="mt-5 font-latin text-xs font-bold tracking-[.2em] text-muted">ERROR {{ status }}</p>
      <h1 class="mt-2 text-2xl font-black sm:text-3xl">{{ content.title }}</h1>
      <p class="mx-auto mt-3 max-w-md text-sm leading-8 text-secondary">{{ content.message }}</p>
      <p class="mx-auto mt-2 max-w-md text-xs leading-6 text-muted">{{ content.hint }}</p>
      <div class="mt-7 flex flex-col justify-center gap-2 sm:flex-row">
        <button type="button" class="ui-primary-button" @click="goHome"><CinematicIcon name="home" class="size-4.5" />بازگشت به خانه</button>
        <button v-if="status !== 404" type="button" class="ui-secondary-button" @click="retry"><CinematicIcon name="refresh" class="size-4.5" />تلاش دوباره</button>
        <NuxtLink v-else to="/search" class="ui-secondary-button"><CinematicIcon name="search" class="size-4.5" />جستجوی فیلم</NuxtLink>
      </div>
    </main>
  </div>
</template>
