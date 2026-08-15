<script setup lang="ts">
const items = [{ title: 'انتخاب آگاهانه', text: 'می‌خواهیم پیدا کردن فیلم و سریال ساده، سریع و قابل‌اعتماد باشد.' }, { title: 'داستان‌های متنوع', text: 'فهرست فعلی برای نمایش امکانات سایت ساخته شده و به‌مرور با عنوان‌های واقعی کامل می‌شود.' }, { title: 'فارسی از ابتدا', text: 'همه بخش‌ها از ابتدا برای زبان فارسی و خواندن از راست به چپ طراحی شده‌اند.' }, { title: 'پیشنهاد قابل‌کنترل', text: 'فقط با اجازه تو از تماشاها و انتخاب‌هایت برای پیشنهاد بهتر استفاده می‌کنیم.' }]
useSeoMeta({ title: 'درباره ما' })
</script>
<template>
  <StaticInfoPage title="درباره روایتو" eyebrow="داستان ما" description="روایتو یک فضای فارسی برای پیدا کردن فیلم و سریال، تماشای راحت و شریک شدن در داستان‌های ماندگار است." :items="items">
    <section class="mt-8 rounded-3xl border border-line bg-surface/70 p-5 sm:p-7" aria-labelledby="tmdb-credit">
      <div class="flex flex-col gap-5 sm:flex-row sm:items-center">
        <a href="https://www.themoviedb.org" target="_blank" rel="noopener noreferrer" class="shrink-0" aria-label="The Movie Database">
          <img src="https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.svg" alt="TMDB" width="64" height="46" class="h-12 w-auto" referrerpolicy="no-referrer" >
        </a>
        <div>
          <h2 id="tmdb-credit" class="font-black text-ink">منبع اطلاعات کاتالوگ</h2>
          <p class="mt-2 text-xs leading-6 text-secondary">This product uses the TMDB API but is not endorsed or certified by TMDB.</p>
          <p class="mt-1 text-xs leading-6 text-secondary">بخشی از متادیتا و تصاویر کاتالوگ از TMDB دریافت می‌شود؛ TMDB هیچ تأیید یا مسئولیتی نسبت به روایتو ندارد.</p>
        </div>
      </div>
    </section>
  </StaticInfoPage>
</template>
