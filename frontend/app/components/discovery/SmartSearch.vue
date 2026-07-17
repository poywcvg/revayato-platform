<script setup lang="ts">
import type { CinematicIconName } from '~/types'

const props = withDefaults(defineProps<{ suggestions?: string[] }>(), {
  suggestions: () => ['اکشن کره‌ای', 'دوبله فارسی', 'سریال جنایی', 'انیمیشن خانوادگی', 'علمی‌تخیلی', 'فیلم کوتاه و سبک'],
})
const query = ref('')
const { trackSearch } = useAnalyticsEvent()
const quickPaths: Array<{ label: string; hint: string; to: string; icon: CinematicIconName }> = [
  { label: 'امشب چی ببینم؟', hint: 'انتخاب با حال‌وهوا', to: '/#mood', icon: 'mood' },
  { label: 'فیلم‌ها را ببین', hint: 'دیدن فهرست فیلم‌ها', to: '/movies', icon: 'movie' },
  { label: 'ادامه تماشا', hint: 'برگشت به آخرین عنوان', to: '/#continue', icon: 'resume' },
]

function submit(value = query.value) {
  const term = value.trim()
  trackSearch(term, 0)
  void navigateTo({ path: '/search', query: term ? { q: term } : {} })
}
</script>

<template>
  <section class="relative z-10 mx-auto mt-5 w-[calc(100%-2rem)] max-w-6xl sm:mt-7" aria-labelledby="smart-search-title">
    <div class="cinema-panel relative isolate overflow-hidden rounded-3xl p-4 sm:p-6">
      <span class="ambient-orb pointer-events-none absolute -left-16 -top-20 -z-10 size-52 rounded-full opacity-40" aria-hidden="true" />
      <div class="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,.65fr)] lg:items-stretch">
        <div class="min-w-0">
          <div class="px-1">
            <p class="inline-flex items-center gap-2 text-[11px] font-black text-energy-300"><span class="size-1.5 rounded-full bg-primary-500" />کشف سریع</p>
            <h2 id="smart-search-title" class="mt-1 text-lg font-black text-white sm:text-xl">داستان بعدی‌ات را پیدا کن</h2>
            <p class="mt-1 text-xs leading-6 text-muted sm:text-sm">عنوان، بازیگر، کارگردان یا حتی حال‌وهوایی که می‌خواهی را جستجو کن.</p>
          </div>
          <form class="mt-4 flex gap-2" role="search" @submit.prevent="submit()">
            <label class="relative min-w-0 flex-1">
              <span class="sr-only">جستجوی فیلم، سریال، بازیگر یا کارگردان</span>
              <CinematicIcon name="search" class="pointer-events-none absolute right-4 top-1/2 size-5 -translate-y-1/2 text-energy-300" />
              <input v-model="query" type="search" autocomplete="off" enterkeyhint="search" placeholder="مثلاً یک معمای جنایی پرتعلیق..." class="h-13 w-full rounded-2xl bg-white/[.065] pr-12 pl-4 text-sm text-white outline-none ring-1 ring-energy-300/15 transition placeholder:text-slate-500 focus:bg-white/[.1] focus:ring-2 focus:ring-energy-400">
            </label>
            <button type="submit" class="action-discovery h-13 shrink-0 px-4 sm:px-5"><span class="hidden sm:inline">جستجو</span><CinematicIcon name="arrow-left" class="size-5" /></button>
          </form>
          <div class="hide-scrollbar mt-3 flex gap-2 overflow-x-auto pb-1" aria-label="جستجوهای پیشنهادی">
            <button v-for="suggestion in props.suggestions.slice(0, 5)" :key="suggestion" type="button" class="min-h-9 shrink-0 rounded-xl bg-white/[.035] px-3 text-[11px] font-bold text-slate-400 ring-1 ring-white/[.07] transition hover:bg-primary-500/10 hover:text-primary-300 hover:ring-primary-500/25" @click="submit(suggestion)">{{ suggestion }}</button>
          </div>
        </div>

        <div class="hide-scrollbar flex snap-x gap-2 overflow-x-auto pb-1 lg:grid lg:grid-cols-1 lg:overflow-visible lg:pb-0" aria-label="مسیرهای شروع سریع">
          <NuxtLink v-for="path in quickPaths" :key="path.to" :to="path.to" class="quick-path-card group flex min-w-[78%] snap-start items-center gap-3 px-3.5 py-3 sm:min-w-[42%] lg:min-w-0">
            <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-primary-500/10 text-primary-300 transition group-hover:bg-primary-500 group-hover:text-night-950"><CinematicIcon :name="path.icon" class="size-5" /></span>
            <span class="min-w-0"><strong class="block truncate text-xs text-ink">{{ path.label }}</strong><span class="mt-0.5 block truncate text-[10px] text-muted">{{ path.hint }}</span></span>
            <CinematicIcon name="chevron-left" class="mr-auto size-3.5 shrink-0 text-muted transition-transform group-hover:-translate-x-0.5 group-hover:text-primary-300" />
          </NuxtLink>
        </div>
      </div>
    </div>
  </section>
</template>
