<script setup lang="ts">
// The download page used to hardcode the build it offered, so every release
// needed an edit here too — and a forgotten one left the page advertising a
// version the directory no longer held. `/api/app/version/` is the same source
// of truth the installed app polls for updates, and it only ever names an APK
// that is actually on disk. These constants are the floor: what the page shows
// before the call answers, and if it never does.
const APP_VERSION_FALLBACK = '1.0.16'
const APP_SIZE_FALLBACK = '۳ مگابایت'
const APK_URL_FALLBACK = '/downloads/revayato-1.0.16.apk'
const STORE_URL = 'https://revayato.com/app'

interface AppRelease {
  available?: boolean
  version_name?: string
  download_url?: string
  size_bytes?: number
}

const { api } = useApi()
const { data: release } = await useAsyncData<AppRelease | null>(
  'android-release',
  // A download page that cannot reach the API still has to render a button.
  () => api<AppRelease>('/app/version/').catch(() => null),
  { default: () => null },
)

const APP_VERSION = computed(() => {
  const named = release.value?.available ? (release.value.version_name || '').trim() : ''
  return named || APP_VERSION_FALLBACK
})

const APK_URL = computed(() => {
  const url = release.value?.available ? (release.value.download_url || '').trim() : ''
  return url || APK_URL_FALLBACK
})

const APP_SIZE = computed(() => {
  const bytes = release.value?.available ? Number(release.value.size_bytes || 0) : 0
  if (!bytes) return APP_SIZE_FALLBACK
  const mb = bytes / (1024 * 1024)
  // One decimal below 10 MB, whole megabytes above — the extra digit stops
  // mattering once the number is big.
  const shown = mb < 10 ? Math.round(mb * 10) / 10 : Math.round(mb)
  return `${shown.toLocaleString('fa-IR')} مگابایت`
})

const features = [
  { icon: 'play', title: 'پخش آنلاین', text: 'پخش روان فیلم و سریال با انتخاب کیفیت و منبع جایگزین خودکار.' },
  { icon: 'subtitle', title: 'زیرنویس و دوبله', text: 'پشتیبانی از زیرنویس فارسی و نسخه‌های دوبله‌شده.' },
  { icon: 'users', title: 'تماشای گروهی', text: 'اتاق بسازید و با دوستانتان هم‌زمان یک فیلم را تماشا کنید.' },
  { icon: 'download', title: 'دانلود آفلاین', text: 'فایل‌ها را داخل خود اپ دانلود کنید و بدون اینترنت ببینید.' },
]

const steps = [
  'فایل نصب (APK) را از دکمهٔ بالا دانلود کنید.',
  'در تنظیمات گوشی، بخش «امنیت»، گزینهٔ «منابع ناشناخته» را برای مرورگر خود فعال کنید.',
  'فایل دانلودشده را باز کنید و نصب را تأیید کنید.',
  'اپ روایتو را باز کنید و با حساب خود وارد شوید.',
]

const copied = ref(false)
async function copyLink() {
  try {
    await navigator.clipboard.writeText(STORE_URL)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    copied.value = false
  }
}

useSeoMeta({
  title: 'اپلیکیشن روایتو',
  description: 'اپلیکیشن اندرویدی روایتو برای پخش آنلاین، دانلود و تماشای گروهی فیلم و سریال.',
})
</script>

<template>
  <div class="page-section pb-12">
    <PageHero
      title="اپلیکیشن روایتو"
      eyebrow="همراه همیشگی تماشا"
      description="تماشای شخصی‌تر، سریع‌تر و همیشه همراه شما. کاتالوگ، جستجو، پخش آنلاین، زیرنویس و تماشای گروهی در یک اپ سبک اندرویدی."
      icon="rocket"
    >
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
        <UiButtonA :href="APK_URL" download variant="primary" size="lg">
          <CinematicIcon name="download" class="size-5" />
          <span>دانلود نسخه {{ APP_VERSION }}</span>
        </UiButtonA>
        <UiButtonA variant="ghost" size="lg" @click="copyLink">
          <CinematicIcon :name="copied ? 'check' : 'share'" class="size-4" />
          <span>{{ copied ? 'لینک کپی شد' : 'کپی لینک صفحه' }}</span>
        </UiButtonA>
      </div>
      <p class="mt-3 text-xs text-muted">
        حجم {{ APP_SIZE }} · نسخه {{ APP_VERSION }} · اندروید ۷ (API 24) و بالاتر
      </p>
    </PageHero>

    <section class="mt-6 grid gap-4 sm:grid-cols-2">
      <article
        v-for="item in features"
        :key="item.title"
        class="info-card ui-surface render-later group relative overflow-hidden p-5 sm:p-6"
      >
        <div class="flex items-center gap-3">
          <span class="grid size-10 place-items-center rounded-xl bg-primary-500/14 text-primary-300 ring-1 ring-primary-500/20">
            <CinematicIcon :name="item.icon" class="size-5" />
          </span>
          <h2 class="text-lg font-black text-ink">{{ item.title }}</h2>
        </div>
        <p class="mt-3 text-sm leading-7 text-secondary">{{ item.text }}</p>
      </article>
    </section>

    <section class="mt-6 ui-surface render-later rounded-3xl border border-line p-5 sm:p-7">
      <h2 class="text-xl font-black text-ink">نصب اپلیکیشن روی اندروید</h2>
      <ol class="mt-4 flex flex-col gap-3">
        <li
          v-for="(step, index) in steps"
          :key="index"
          class="flex items-start gap-3 text-sm leading-7 text-secondary"
        >
          <span class="grid size-7 shrink-0 place-items-center rounded-full bg-primary-500/14 text-xs font-black text-primary-300 ring-1 ring-primary-500/20 tabular-nums">
            {{ String(index + 1).padStart(2, '0') }}
          </span>
          <span>{{ step }}</span>
        </li>
      </ol>
      <p class="mt-5 rounded-2xl bg-elevated p-4 text-xs leading-6 text-muted ring-1 ring-line">
        نکته: چون اپلیکیشن از فروشگاه رسمی (Google Play) منتشر نشده، اندروید هنگام نصب هشدار می‌دهد. این طبیعی است؛ فایل مستقیماً از سرور روایتو بارگذاری می‌شود.
      </p>
    </section>

    <section class="mt-6 ui-surface render-later rounded-3xl border border-line p-5 sm:p-7">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 class="text-xl font-black text-ink">لینک مستقیم فایل</h2>
          <p class="mt-1 text-xs text-muted">در صورت نیاز می‌توانید لینک زیر را کپی کنید.</p>
        </div>
        <code dir="ltr" class="select-all rounded-xl bg-elevated px-3 py-2 text-xs text-secondary ring-1 ring-line">{{ APK_URL }}</code>
      </div>
      <div class="mt-4 flex flex-wrap gap-3">
        <UiButtonA :href="APK_URL" download variant="primary" size="md">
          <CinematicIcon name="download" class="size-4" />
          <span>دانلود مستقیم APK</span>
        </UiButtonA>
      </div>
    </section>
  </div>
</template>
