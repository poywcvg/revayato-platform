<script setup lang="ts">
const year = new Date().getFullYear()
const links = [
  { label: 'درباره ما', to: '/about' },
  { label: 'تماس', to: '/contact' },
  { label: 'قوانین', to: '/terms' },
  { label: 'حریم خصوصی', to: '/privacy' },
  { label: 'گزارش مشکل', to: '/contact?subject=report' },
]
</script>

<template>
  <footer class="app-footer mobile-nav-safe relative overflow-hidden border-t border-line text-secondary">
    <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-primary-500/45 to-transparent" aria-hidden="true" />
    <div class="mx-auto flex max-w-[1600px] flex-col gap-7 px-5 py-8 sm:px-8 lg:flex-row lg:items-center lg:justify-between">
      <AppLogo :compact-on-mobile="false" />
      <nav aria-label="پیوندهای فوتر">
        <ul class="flex flex-wrap gap-x-1 gap-y-2">
          <li v-for="item in links" :key="item.label">
            <NuxtLink :to="item.to" class="inline-flex min-h-11 items-center rounded-xl px-3 text-sm font-bold text-slate-400 transition-colors hover:bg-white/[.05] hover:text-primary-300">
              {{ item.label }}
            </NuxtLink>
          </li>
        </ul>
      </nav>
    </div>

    <div class="border-t border-line">
      <div class="mx-auto flex max-w-[1600px] flex-col gap-3 px-5 py-5 text-[11px] text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p>© {{ year }} روایتو؛ همه حقوق محفوظ است.</p>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
          <p class="inline-flex items-center gap-1.5"><CinematicIcon name="shield-check" class="size-4 text-primary-400" />رده سنی و هشدار محتوا پیش از پخش</p>
          <a href="#main-content" class="inline-flex min-h-11 items-center gap-1 font-bold text-slate-400 transition-colors hover:text-primary-300"><CinematicIcon name="arrow-up" class="size-4" />بازگشت به بالا</a>
        </div>
      </div>
    </div>
  </footer>
</template>
