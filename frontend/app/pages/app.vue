<script setup lang="ts">
const APP_VERSION = '5.0.2'
const APP_SIZE = '۷٫۴ مگابایت'
const APK_URL = '/downloads/revayato-native-v5.0.2.apk'
const STORE_URL = 'https://revayato.com/app'

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
        <a
          :href="APK_URL"
          download
          class="inline-flex items-center justify-center gap-2.5 rounded-2xl bg-primary-500 px-7 py-4 text-base font-black text-ink shadow-[0_10px_30px_-10px_theme(colors.primary.500)] transition-transform duration-150 hover:-translate-y-0.5 active:translate-y-0"
        >
          <CinematicIcon name="download" class="size-5" />
          <span>دانلود نسخه {{ APP_VERSION }}</span>
        </a>
        <button
          type="button"
          class="inline-flex items-center justify-center gap-2 rounded-2xl bg-elevated px-5 py-4 text-sm font-bold text-secondary ring-1 ring-line transition-colors hover:text-ink"
          @click="copyLink"
        >
          <CinematicIcon :name="copied ? 'check' : 'share'" class="size-4" />
          <span>{{ copied ? 'لینک کپی شد' : 'کپی لینک صفحه' }}</span>
        </button>
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
        <a :href="APK_URL" download class="inline-flex items-center gap-2 rounded-xl bg-primary-500 px-5 py-3 text-sm font-black text-ink">
          <CinematicIcon name="download" class="size-4" />
          <span>دانلود مستقیم APK</span>
        </a>
      </div>
    </section>
  </div>
</template>
