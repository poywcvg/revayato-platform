<script setup lang="ts">
const features = [
  {
    icon: 'play' as const,
    title: 'تماشای آنلاین',
    text: 'هر کیفیت را مستقیم در پخش‌کننده سایت ببین؛ بدون نیاز به دانلود اجباری.',
  },
  {
    icon: 'download' as const,
    title: 'دانلود بر اساس کیفیت',
    text: 'لینک‌های ۱۰۸۰، ۷۲۰ و بقیه کیفیت‌ها مرتب روی صفحه فیلم و سریال قرار می‌گیرند.',
  },
  {
    icon: 'users' as const,
    title: 'تماشای گروهی',
    text: 'اتاق خصوصی بساز و هم‌زمان با دوستانت پخش و گفت‌وگو را زنده نگه دار.',
  },
  {
    icon: 'sparkles' as const,
    title: 'پیشنهاد هوشمند',
    text: 'بر اساس تماشاها و علاقه‌هایت، عنوان‌های نزدیک به سلیقه‌ات را پیدا کن.',
  },
  {
    icon: 'user' as const,
    title: 'بازیگران و فیلم‌شناسی',
    text: 'از صفحه بازیگر به فیلم‌ها و سریال‌هایش برو و مسیر کشف را ادامه بده.',
  },
  {
    icon: 'globe' as const,
    title: 'کشور، دوبله و زیرنویس',
    text: 'با فیلتر کشور، دوبله فارسی و زیرنویس سریع‌تر به نسخه مناسب برس.',
  },
]

useSeoMeta({
  title: 'امکانات روایتو',
  description: 'تماشای آنلاین، دانلود با کیفیت، تماشای گروهی، پیشنهاد هوشمند و کاتالوگ فارسی فیلم و سریال در روایتو.',
})
</script>

<template>
  <div class="cinema-page overflow-x-clip pb-14">
    <section class="page-section pb-0">
      <div class="page-hero relative overflow-hidden rounded-[1.75rem] p-5 sm:p-8 lg:p-10">
        <div class="grid items-end gap-8 lg:grid-cols-[minmax(0,1fr)_19rem]">
          <div>
            <p class="text-xs font-black tracking-wide text-brand">به روایتو خوش آمدی</p>
            <h1 class="mt-3 max-w-4xl text-[clamp(1.875rem,5vw,3.75rem)] font-black leading-tight text-balance text-ink">
              هر فیلم یک خاطره؛ داستان بعدی‌ات را پیدا کن
            </h1>
            <p class="mt-4 max-w-2xl text-sm leading-8 text-secondary sm:text-base">
              فیلم و سریال را در یک کاتالوگ فارسی پیدا کن، آنلاین ببین، برای بعد نگه دار یا تماشا را با دوستانت شریک شو.
            </p>
            <div class="mt-7 flex flex-col gap-3 min-[420px]:flex-row min-[420px]:flex-wrap">
              <NuxtLink to="/movies" class="action-primary"><CinematicIcon name="movie" class="size-5" />شروع تماشا</NuxtLink>
              <NuxtLink to="/watch-party" class="ui-secondary-button">
                <CinematicIcon name="users" class="size-5 text-brand" />
                تماشای گروهی
              </NuxtLink>
            </div>
          </div>

          <aside class="ui-surface grid gap-2 p-3 sm:grid-cols-3 lg:grid-cols-1" aria-label="مسیرهای سریع">
            <NuxtLink to="/movies" class="quick-path-card flex min-h-14 items-center gap-3 px-3">
              <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-primary-500/12 text-brand"><CinematicIcon name="movie" class="size-4.5" /></span>
              <span><strong class="block text-xs font-black text-ink">فیلم‌ها</strong><small class="text-[10px] text-muted">از کلاسیک تا تازه‌ها</small></span>
            </NuxtLink>
            <NuxtLink to="/series" class="quick-path-card flex min-h-14 items-center gap-3 px-3">
              <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-primary-500/12 text-brand"><CinematicIcon name="series" class="size-4.5" /></span>
              <span><strong class="block text-xs font-black text-ink">سریال‌ها</strong><small class="text-[10px] text-muted">قسمت بعدی منتظر توست</small></span>
            </NuxtLink>
            <NuxtLink to="/actors" class="quick-path-card flex min-h-14 items-center gap-3 px-3">
              <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-primary-500/12 text-brand"><CinematicIcon name="user" class="size-4.5" /></span>
              <span><strong class="block text-xs font-black text-ink">بازیگران</strong><small class="text-[10px] text-muted">فیلم‌شناسی چهره‌ها</small></span>
            </NuxtLink>
          </aside>
        </div>
      </div>
    </section>

    <section class="content-section" aria-labelledby="features-title">
      <SectionHeader
        id="features-title"
        title="امکاناتی که تجربه تماشا را کامل می‌کند"
        eyebrow="چرا روایتو"
        description="هر بخش یک کار مشخص دارد؛ از پیدا کردن عنوان تا پخش، دانلود و اشتراک با دوستان."
        icon="sparkles"
      />
      <div class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="feature in features"
          :key="feature.title"
          class="info-card ui-surface p-5 sm:p-6"
        >
          <span class="grid size-11 place-items-center rounded-2xl bg-primary-500/15 text-primary-300 ring-1 ring-primary-500/25">
            <CinematicIcon :name="feature.icon" class="size-5" />
          </span>
          <h2 class="mt-4 text-lg font-black text-ink">{{ feature.title }}</h2>
          <p class="mt-2 text-sm leading-7 text-secondary">{{ feature.text }}</p>
        </article>
      </div>
    </section>

    <section class="content-section">
      <div class="page-hero relative isolate overflow-hidden rounded-[1.75rem] px-5 py-7 sm:px-8 sm:py-9">
        <span class="pointer-events-none absolute -left-16 top-0 -z-10 size-52 rounded-full bg-elevated/35 blur-3xl" aria-hidden="true" />
        <div class="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-[11px] font-black tracking-wide text-muted">همین حالا</p>
            <h2 class="mt-1 text-xl font-black text-ink sm:text-2xl">کاتالوگ را باز کن و از تازه‌ترین عنوان‌ها شروع کن</h2>
            <p class="mt-2 max-w-2xl text-sm leading-7 text-secondary">فیلم‌های جدید و به‌روز‌شده اول صفحه اصلی می‌آیند تا همیشه نزدیک‌ترین نسخه را ببینی.</p>
          </div>
          <NuxtLink to="/" class="action-primary w-full shrink-0 sm:w-auto"><CinematicIcon name="home" class="size-5" />رفتن به خانه</NuxtLink>
        </div>
      </div>
    </section>
  </div>
</template>
