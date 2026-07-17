<script setup lang="ts">
import type { Movie } from '~/types'

const props = defineProps<{ item: Movie }>()
const modalOpen = ref(false)
const requestedMode = ref<'full' | 'trailer'>('full')
const activeSection = ref('story')
const { catalog } = useCatalog()
const related = useRelatedMovies(() => props.item, 8)
const { isLiked, toggleLike } = useLibrary()
const { trackGenreClick, trackLikeAction, trackTitleView, trackPersonClick } = useAnalyticsEvent()
const liked = computed(() => isLiked(props.item.id))
const restricted = computed(() => props.item.age_rating === '18+')
const episodeCount = computed(() => props.item.episodes?.length || 0)
const primaryGenre = computed(() => props.item.genres[0])
const sameGenreTitles = computed(() => {
  if (!primaryGenre.value) return []
  return catalog.value
    .filter(candidate => candidate.id !== props.item.id && candidate.genres.some(genre => genre.slug === primaryGenre.value?.slug))
    .sort((a, b) => b.rating - a.rating || b.popularity - a.popularity)
    .slice(0, 8)
})
const playLabel = computed(() => props.item.progress_percent > 0 ? 'ادامه تماشا' : props.item.type === 'series' ? 'پخش قسمت اول' : 'تماشا')
const detailTabs = computed(() => [
  { id: 'story', label: 'داستان' },
  { id: 'cast', label: 'بازیگران' },
  { id: 'director', label: 'کارگردان' },
  ...(props.item.type === 'series' ? [{ id: 'episodes', label: 'فصل‌ها و قسمت‌ها' }] : []),
  { id: 'comments', label: 'نظرات کاربران' },
  { id: 'similar', label: 'مشابه‌ها' },
  { id: 'why-recommended', label: 'چرا پیشنهاد شده؟' },
])
const mockComments = [
  { name: 'سارا', score: 9, text: 'فضاسازی و ریتم داستان خیلی خوب بود؛ مخصوصاً نیمه دوم که جزئیات به هم وصل می‌شوند.' },
  { name: 'مانی', score: 8, text: 'انتخاب بازیگران و موسیقی حس منسجمی ساخته؛ ارزش یک‌بار تماشا را دارد.' },
]

function watchPath(confirmed = false) {
  const query = new URLSearchParams({ mode: requestedMode.value, type: props.item.type })
  if (confirmed) query.set('confirmed', '1')
  return `/watch/${props.item.slug}?${query.toString()}`
}

function requestPlay(mode: 'full' | 'trailer') {
  requestedMode.value = mode
  if (restricted.value) modalOpen.value = true
  else void navigateTo(watchPath())
}

function confirmPlay() {
  modalOpen.value = false
  void navigateTo(watchPath(true))
}

function toggleLiked() {
  const nextLiked = !liked.value
  toggleLike(props.item.id)
  trackLikeAction(props.item, nextLiked)
}

function activateSection(id: string) {
  activeSection.value = id
}

onMounted(() => trackTitleView(props.item))
</script>

<template>
  <article class="overflow-clip bg-night-950 text-white">
    <section class="relative isolate min-h-[680px] overflow-hidden bg-night-950 text-white sm:min-h-[680px]">
      <NuxtImg :src="item.backdrop_url" alt="" class="absolute inset-0 -z-30 h-full w-full object-cover object-center" preload sizes="100vw" />
      <div class="absolute inset-0 -z-20 bg-gradient-to-l from-night-950 via-night-950/88 to-night-900/30" />
      <div class="absolute inset-0 -z-10 bg-gradient-to-t from-night-950 via-night-950/20 to-black/25" />
      <div class="ambient-orb pointer-events-none absolute -right-36 top-20 -z-10 h-80 w-80 rounded-full" />

      <div class="page-shell flex min-h-[680px] flex-col justify-end py-7 sm:min-h-[680px] sm:py-12">
        <nav class="mb-auto flex items-center gap-2 pt-3 text-[11px] font-bold text-slate-400" aria-label="مسیر صفحه">
          <NuxtLink to="/" class="inline-flex min-h-10 items-center rounded-lg px-1 transition hover:bg-white/5 hover:text-primary-300">خانه</NuxtLink><CinematicIcon name="chevron-left" class="size-3.5" /><NuxtLink :to="item.type === 'movie' ? '/movies' : '/series'" class="inline-flex min-h-10 items-center rounded-lg px-1 transition hover:bg-white/5 hover:text-primary-300">{{ item.type === 'movie' ? 'فیلم‌ها' : 'سریال‌ها' }}</NuxtLink><CinematicIcon name="chevron-left" class="size-3.5" /><span class="max-w-36 truncate text-slate-200">{{ item.title }}</span>
        </nav>

        <div class="grid items-end gap-6 sm:grid-cols-[180px_minmax(0,1fr)] lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-9">
          <div class="relative mx-auto w-40 overflow-hidden rounded-2xl shadow-2xl ring-1 ring-white/15 sm:mx-0 sm:w-full">
            <NuxtImg :src="item.poster_url" :alt="`پوستر ${item.title}`" class="aspect-[2/3] w-full object-cover" preload sizes="(max-width: 639px) 144px, (max-width: 1023px) 180px, 220px" />
            <div v-if="item.progress_percent" class="absolute inset-x-0 bottom-0 bg-night-950/95 px-3 py-2">
              <div class="flex items-center justify-between text-[9px] font-black text-slate-300"><span>پیشرفت تماشا</span><span class="text-primary-300">{{ item.progress_percent }}٪</span></div>
              <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-white/15"><div class="h-full rounded-full bg-primary-500" :style="{ width: `${item.progress_percent}%` }" /></div>
            </div>
          </div>

          <div class="flex min-w-0 max-w-4xl flex-col pb-1">
            <div class="order-1 flex flex-wrap items-center gap-2"><span class="rounded-lg bg-primary-500 px-2.5 py-1 text-[10px] font-black text-night-950">{{ item.type === 'movie' ? 'فیلم سینمایی' : 'سریال' }}</span><AgeRatingBadge :rating="item.age_rating" show-label /><DubSubtitleBadge :is-dubbed="item.is_dubbed" :has-subtitle="item.has_subtitle" dark /></div>
            <p class="order-2 mt-4 w-full truncate text-right text-xs font-bold tracking-[.16em] text-energy-300" dir="ltr">{{ item.original_title }}</p>
            <h1 class="order-3 mt-1 text-4xl font-black leading-tight tracking-tight text-balance sm:text-5xl lg:text-6xl">{{ item.title }}</h1>
            <p class="order-5 mt-3 line-clamp-3 max-w-3xl text-sm leading-7 text-slate-300 sm:order-4 sm:text-base">{{ item.description }}</p>

            <div class="order-6 mt-4 flex flex-wrap gap-2 sm:order-5">
              <NuxtLink v-for="genre in item.genres" :key="genre.id" :to="{ path: item.type === 'movie' ? '/movies' : '/series', query: { genre: genre.slug } }" class="inline-flex min-h-10 items-center rounded-lg bg-white/[.07] px-3 py-1.5 text-xs font-bold text-slate-200 ring-1 ring-white/10 transition hover:bg-primary-500 hover:text-night-950 hover:ring-primary-400" @click="trackGenreClick(genre.slug)">{{ genre.title }}</NuxtLink>
            </div>

            <DetailMetadata :item="item" class="order-7 mt-5 sm:order-6" />

            <div class="order-4 mt-5 grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2.5 sm:order-7 sm:mt-6 sm:flex sm:flex-wrap">
              <button type="button" class="action-primary col-span-3 w-full sm:w-auto" @click="requestPlay('full')"><CinematicIcon name="play" class="size-5" filled />{{ playLabel }}</button>
              <button type="button" class="inline-flex min-h-12 items-center gap-2 rounded-[.875rem] bg-white/[.08] px-5 text-sm font-black text-white ring-1 ring-white/15 transition hover:bg-white/15 hover:ring-energy-300/30" @click="requestPlay('trailer')"><CinematicIcon name="trailer" class="size-5 text-energy-300" />پخش تریلر</button>
              <WatchlistButton :id="item.id" :slug="item.slug" :content-type="item.type" dark compact-on-mobile />
              <button type="button" class="inline-flex min-h-12 min-w-12 items-center justify-center gap-2 rounded-xl px-3 text-sm font-black transition sm:px-4" :class="liked ? 'bg-error text-ink' : 'bg-white/[.08] text-ink ring-1 ring-white/15 hover:bg-white/15'" :aria-label="liked ? 'حذف پسند' : 'پسندیدن'" :aria-pressed="liked" @click="toggleLiked"><CinematicIcon name="heart" class="size-5" :filled="liked" :stroke-width="liked ? 2.25 : 1.8" /><span class="hidden sm:inline">{{ liked ? 'پسندیده شد' : 'پسندیدن' }}</span></button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <nav class="sticky top-[132px] z-30 border-y border-white/8 bg-night-950/98 md:top-[68px]" aria-label="بخش‌های صفحه عنوان">
      <div class="page-shell hide-scrollbar flex gap-1 overflow-x-auto py-2">
        <a v-for="tab in detailTabs" :key="tab.id" :href="`#${tab.id}`" class="inline-flex min-h-11 shrink-0 items-center rounded-xl px-3 py-2 text-xs font-bold transition" :class="activeSection === tab.id ? 'bg-primary-500 text-night-950' : 'text-slate-400 hover:bg-white/5 hover:text-white'" @click="activateSection(tab.id)">{{ tab.label }}</a>
      </div>
    </nav>

    <div class="cinema-page">
      <div class="page-shell grid gap-8 py-10 lg:grid-cols-[minmax(0,1fr)_310px] lg:py-14">
        <div class="min-w-0 space-y-11">
          <section id="story" class="scroll-mt-40 rounded-3xl bg-white/[.035] p-5 ring-1 ring-white/8 sm:p-7" aria-labelledby="story-title">
            <p class="text-xs font-black text-primary-400">خلاصه داستان</p><h2 id="story-title" class="mt-1 text-2xl font-black text-white">درباره {{ item.title }}</h2><p class="mt-4 max-w-3xl text-sm leading-8 text-slate-300 sm:text-base">{{ item.description }}</p>
          </section>

          <ContentWarnings :warnings="item.content_warnings" />

          <section id="cast" class="scroll-mt-40" aria-labelledby="cast-title">
            <SectionHeader id="cast-title" title="بازیگران و عوامل" eyebrow="پشت و جلوی دوربین" dark />
            <div class="hide-scrollbar flex gap-3 overflow-x-auto pb-3">
              <button v-for="person in item.cast" :key="person.id" type="button" class="w-32 shrink-0 rounded-2xl bg-white/[.035] p-3 text-center ring-1 ring-white/8 transition hover:-translate-y-0.5 hover:bg-white/[.07] hover:ring-energy-300/25" @click="trackPersonClick('cast', person.name, item)">
                <NuxtImg v-if="person.photo_url" :src="person.photo_url" :alt="person.name" class="mx-auto h-20 w-20 rounded-full object-cover ring-2 ring-white/10" loading="lazy" />
                <span v-else class="mx-auto grid h-20 w-20 place-items-center rounded-full bg-gradient-to-br from-energy-500 to-night-800 text-xl font-black text-night-950 ring-4 ring-night-900">{{ person.name.slice(0, 1) }}</span>
                <h3 class="mt-3 truncate text-sm font-black text-white">{{ person.name }}</h3><p class="mt-0.5 truncate text-xs text-slate-500">{{ person.role }}</p>
              </button>
              <button v-for="person in item.crew" :key="`crew-${person.id}`" type="button" class="w-32 shrink-0 rounded-2xl bg-white/[.035] p-3 text-center ring-1 ring-white/8 transition hover:-translate-y-0.5 hover:bg-white/[.07] hover:ring-primary-400/30" @click="trackPersonClick('director', person.name, item)"><span class="mx-auto grid h-20 w-20 place-items-center rounded-full bg-gradient-to-br from-primary-400 to-primary-700 text-xl font-black text-night-950 ring-4 ring-night-900">{{ person.name.slice(0, 1) }}</span><h3 class="mt-3 truncate text-sm font-black text-white">{{ person.name }}</h3><p class="mt-0.5 truncate text-xs text-slate-500">{{ person.job }}</p></button>
            </div>
          </section>

          <EpisodeList v-if="item.type === 'series'" :item="item" />

          <section id="director" class="scroll-mt-40 rounded-3xl bg-white/[.04] p-5 ring-1 ring-white/10 sm:p-6">
            <p class="text-xs font-black text-primary-400">نگاه خالق اثر</p><div class="mt-3 flex items-center gap-4"><span class="grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-primary-400 to-primary-700 text-xl font-black text-night-950">{{ item.director.slice(0, 1) }}</span><div><h2 class="text-lg font-black text-white">{{ item.director }}</h2><p class="mt-1 text-sm leading-6 text-slate-400">کارگردان {{ item.type === 'movie' ? 'این فیلم' : 'و خالق این سریال' }}؛ آثار نزدیک به جهان این عنوان را کشف کن.</p><button type="button" class="mt-2 text-xs font-black text-primary-400 transition hover:text-primary-300" @click="trackPersonClick('director', item.director, item)">دنبال‌کردن آثار این کارگردان</button></div></div>
          </section>

          <section id="comments" class="scroll-mt-40" aria-labelledby="comments-title">
            <SectionHeader id="comments-title" title="نظرات کاربران" eyebrow="گفت‌وگوی بدون اسپویل" dark />
            <div class="grid gap-3 sm:grid-cols-2"><article v-for="comment in mockComments" :key="comment.name" class="rounded-2xl bg-white/[.035] p-4 ring-1 ring-white/8"><div class="flex items-center justify-between gap-3"><strong class="text-sm text-white">{{ comment.name }}</strong><span class="inline-flex items-center gap-1 text-xs font-black text-primary-400"><CinematicIcon name="star" class="size-4" filled />{{ comment.score }}/۱۰</span></div><p class="mt-3 text-xs leading-6 text-slate-400">{{ comment.text }}</p></article></div>
            <button type="button" disabled class="mt-3 inline-flex min-h-11 items-center gap-2 rounded-xl bg-white/[.035] px-4 py-2.5 text-xs font-black text-muted ring-1 ring-white/8"><CinematicIcon name="comment" class="size-4" />نوشتن نظر<span class="rounded-md bg-elevated px-1.5 py-0.5 text-[9px]">به‌زودی</span></button>
          </section>

          <section id="why-recommended" class="scroll-mt-40 rounded-3xl bg-gradient-to-l from-energy-500/10 to-primary-500/8 p-5 ring-1 ring-energy-300/15 sm:p-6"><div class="flex items-start gap-4"><span class="grid size-12 shrink-0 place-items-center rounded-2xl bg-energy-500/14 text-energy-300 ring-1 ring-energy-400/20"><CinematicIcon name="ai" class="size-7" /></span><div><p class="text-xs font-black text-energy-300">چرا پیشنهاد شده؟</p><h2 class="mt-1 text-lg font-black text-white">{{ item.recommendation_reason || 'کاربرانی با انتخاب‌های نزدیک، این عنوان را دوست داشته‌اند' }}</h2><p class="mt-2 text-xs leading-6 text-slate-400">این پیشنهاد فقط از انتخاب‌های اختیاری تو در همین سایت ساخته می‌شود. کارهای تو در سایت‌های دیگر بررسی نمی‌شود.</p><NuxtLink to="/profile#personalization" class="mt-3 inline-flex min-h-10 items-center text-xs font-black text-energy-300 hover:text-energy-200">تنظیم پیشنهادها</NuxtLink></div></div></section>
        </div>

        <aside class="h-fit space-y-5 lg:sticky lg:top-28">
          <div class="rounded-2xl bg-white/[.04] p-5 ring-1 ring-white/10">
            <div class="flex items-center justify-between gap-3"><h2 class="font-black text-ink">در یک نگاه</h2><span class="inline-flex items-center gap-1 text-[10px] font-black text-success"><span class="h-1.5 w-1.5 rounded-full bg-success" />منتشر شده</span></div>
            <dl class="mt-4 divide-y divide-white/8 text-sm"><div class="flex items-start justify-between gap-4 py-3 first:pt-0"><dt class="text-slate-500">نوع محتوا</dt><dd class="font-bold text-slate-200">{{ item.type === 'movie' ? 'فیلم' : 'سریال' }}</dd></div><div class="flex items-start justify-between gap-4 py-3"><dt class="text-slate-500">کارگردان</dt><dd class="max-w-40 text-left"><button type="button" class="font-bold text-slate-200 transition hover:text-primary-400" @click="trackPersonClick('director', item.director, item)">{{ item.director }}</button></dd></div><div class="flex items-start justify-between gap-4 py-3"><dt class="text-slate-500">رده سنی</dt><dd><AgeRatingBadge :rating="item.age_rating" /></dd></div><div class="flex items-start justify-between gap-4 py-3"><dt class="text-slate-500">نسخه پخش</dt><dd class="text-left text-xs font-bold text-slate-300">{{ item.is_dubbed ? 'دوبله فارسی' : item.has_subtitle ? 'زیرنویس فارسی' : 'زبان اصلی' }}</dd></div><div v-if="item.type === 'series'" class="flex items-start justify-between gap-4 py-3"><dt class="text-slate-500">قسمت‌ها</dt><dd class="font-bold text-slate-200">{{ episodeCount || 'به‌زودی' }}</dd></div></dl>
          </div>
          <div class="rounded-2xl bg-white/[.04] p-5 ring-1 ring-white/10"><RatingWidget :object-id="item.id" :slug="item.slug" :content-type="item.type" :initial-rating="item.rating" dark /></div>
          <div class="hidden rounded-2xl bg-primary-500 p-5 text-night-950 lg:block"><CinematicIcon name="resume" class="size-8" /><h2 class="mt-3 font-black">آماده تماشا هستی؟</h2><p class="mt-1 text-xs leading-6 text-night-900/75">پخش از همان جایی که رها کردی ادامه پیدا می‌کند.</p><button type="button" class="mt-4 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-xl bg-night-950 px-4 text-xs font-black text-white transition hover:bg-night-900" @click="requestPlay('full')"><CinematicIcon name="play" class="size-4" filled />{{ playLabel }}</button></div>
        </aside>
      </div>

      <LazyMovieRow v-if="sameGenreTitles.length" :hydrate-on-visible="{ rootMargin: '320px 0px' }" :title="`بیشتر از ژانر ${primaryGenre?.title}`" eyebrow="در همان حال‌وهوا" :items="sameGenreTitles" :href="`/${item.type === 'movie' ? 'movies' : 'series'}?genre=${primaryGenre?.slug}`" dark />
      <LazyMovieRow v-if="related.length" id="similar" :hydrate-on-visible="{ rootMargin: '320px 0px' }" title="مشابه‌ها" eyebrow="انتخاب‌های نزدیک به این عنوان" :items="related" :href="item.type === 'movie' ? '/movies' : '/series'" dark />
      <div class="h-12" />
    </div>
  </article>

  <ConfirmAdultContentModal :open="modalOpen" :title="item.title" @close="modalOpen = false" @confirm="confirmPlay" />
</template>
