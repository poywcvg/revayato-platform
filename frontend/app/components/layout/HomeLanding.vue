<script setup lang="ts">
const { catalog, genres, pending, error, loadFromApi, resetToMock } = useCatalog()
const route = useRoute()
const heroItems = computed(() => [...catalog.value]
  .filter(item => item.backdrop_url && item.poster_url)
  .sort((a, b) => Number(b.is_trending) * 5 + Number(b.is_new) * 3 + Number(b.is_recommended) * 2 + b.popularity / 100
    - (Number(a.is_trending) * 5 + Number(a.is_new) * 3 + Number(a.is_recommended) * 2 + a.popularity / 100))
  .slice(0, 6))
const railLimit = 6
const trending = computed(() => catalog.value.filter(item => item.is_trending).slice(0, railLimit))
const newReleases = computed(() => [...catalog.value].sort((a, b) => Number(b.is_new) - Number(a.is_new) || b.year - a.year).slice(0, railLimit))
const dubbed = computed(() => catalog.value.filter(item => item.is_dubbed).slice(0, railLimit))
const recommendedSeries = computed(() => catalog.value.filter(item => item.type === 'series' && item.is_recommended).slice(0, railLimit))
const familyAnimation = computed(() => catalog.value.filter(item => item.format === 'animation' || item.genres.some(genre => ['family', 'kids', 'animation'].includes(genre.slug))).slice(0, railLimit))
const { recommendations: recommended, isPersonalized, personalizationLevel } = usePersonalizedRecommendations(railLimit)
const recommendationEyebrow = computed(() => ({
  cold_start: 'انتخاب هوشمند برای شروع',
  learning: 'در حال شناخت سلیقه تو',
  growing: 'هماهنگ با رفتار اخیر تو',
  tuned: 'تنظیم‌شده برای سلیقه تو',
}[personalizationLevel.value]))
const continueWatching = computed(() => catalog.value.filter(item => item.progress_percent > 0).slice(0, 4))
const hasContinue = computed(() => continueWatching.value.length > 0)
const weeklyFeatured = computed(() => catalog.value.find(item => item.slug === 'third-gate') || catalog.value.find(item => item.is_recommended) || catalog.value[0])
const activeCategory = ref('all')
const activeMood = ref('')
const { trackFilterApply } = useAnalyticsEvent()

const categoryOptions = computed(() => [
  { label: 'منتخب‌ها', value: 'all', icon: 'sparkles' as const },
  { label: 'فیلم', value: 'movie', icon: 'movie' as const },
  { label: 'سریال', value: 'series', icon: 'series' as const },
  { label: 'انیمیشن', value: 'animation', icon: 'animation' as const },
  { label: 'دوبله فارسی', value: 'dubbed', icon: 'audio' as const },
  ...genres
    .filter(genre => ['action', 'thriller', 'comedy', 'sci-fi', 'family'].includes(genre.slug))
    .map(genre => ({ label: genre.title, value: `genre:${genre.slug}`, icon: genre.icon })),
])

const categoryItems = computed(() => {
  const value = activeCategory.value
  if (value === 'all') return [...catalog.value].sort((a, b) => b.popularity - a.popularity).slice(0, 8)
  if (value === 'movie' || value === 'series') return catalog.value.filter(item => item.type === value).slice(0, 8)
  if (value === 'animation') return familyAnimation.value
  if (value === 'dubbed') return dubbed.value
  const genre = value.replace('genre:', '')
  return catalog.value.filter(item => item.genres.some(itemGenre => itemGenre.slug === genre)).slice(0, 8)
})

const activeCategoryLabel = computed(() => categoryOptions.value.find(option => option.value === activeCategory.value)?.label || 'منتخب‌ها')

const moodItems = computed(() => {
  const rules: Record<string, (item: typeof catalog.value[number]) => boolean> = {
    exciting: item => item.genres.some(genre => ['action', 'adventure', 'thriller'].includes(genre.slug)),
    calm: item => item.genres.some(genre => ['drama', 'romance', 'family'].includes(genre.slug)) && !item.is_uncensored,
    scary: item => item.genres.some(genre => ['horror', 'mystery', 'thriller'].includes(genre.slug)),
    romantic: item => item.genres.some(genre => genre.slug === 'romance'),
    thoughtful: item => item.genres.some(genre => ['sci-fi', 'mystery', 'psychological'].includes(genre.slug)),
    family: item => item.age_rating === '12+' && !item.is_uncensored,
    light: item => item.duration_minutes <= 105 || item.format === 'short',
  }
  return activeMood.value ? catalog.value.filter(rules[activeMood.value] || (() => true)).slice(0, 8) : []
})

const collections = computed(() => [
  {
    title: 'جهان‌های تاریک و فانتزی',
    description: 'دروازه‌ها، افسانه‌ها و دنیاهایی که قوانین خودشان را دارند.',
    items: catalog.value.filter(item => item.genres.some(genre => genre.slug === 'fantasy')).slice(0, 3),
    href: '/movies?genre=fantasy',
    accent: 'فانتزی منتخب',
  },
  {
    title: 'اکشن‌های پرریتم',
    description: 'برای شب‌هایی که داستانی سریع، پرتنش و بدون مکث می‌خواهی.',
    items: catalog.value.filter(item => item.genres.some(genre => ['action', 'crime', 'thriller'].includes(genre.slug))).slice(0, 3),
    href: '/movies?genre=action',
    accent: 'انرژی بالا',
  },
  {
    title: 'رازهای حل‌نشده',
    description: 'معماها، پرونده‌ها و سرنخ‌هایی که تا پایان رهایت نمی‌کنند.',
    items: catalog.value.filter(item => item.genres.some(genre => ['mystery', 'crime'].includes(genre.slug))).slice(0, 3),
    href: '/movies?genre=mystery',
    accent: 'پر از تعلیق',
  },
].filter(collection => collection.items.length))

watch(activeCategory, value => trackFilterApply('home_category', value))
watch(activeMood, value => value && trackFilterApply('mood', value))

async function revealRequestedSection(section: unknown) {
  if (!import.meta.client || section !== 'recommended') return
  await nextTick()
  document.getElementById('recommended')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(() => route.query.section, revealRequestedSection)
onMounted(() => { void revealRequestedSection(route.query.section) })
useSeoMeta({ title: 'خانه', description: 'در روایتو فیلم و سریال را پیدا کن، تماشا کن و تجربه‌ات را با دوستانت به اشتراک بگذار.' })
</script>

<template>
  <div class="cinema-page overflow-x-clip pb-16">
    <HeroMovieSlider :items="heroItems" />
    <SmartSearch />
    <CatalogSourceNotice class="content-section pt-4" :error="error" :pending="pending" @retry="loadFromApi" @dismiss="resetToMock" />

    <section class="content-section pt-9 sm:pt-12" aria-labelledby="home-categories-title">
      <div class="relative overflow-hidden rounded-3xl border border-line bg-canvas-soft/75 p-4 sm:p-6">
        <span class="pointer-events-none absolute -left-24 -top-24 size-64 rounded-full bg-primary-500/[.06] blur-3xl" aria-hidden="true" />
        <SectionHeader id="home-categories-title" title="سریع‌تر به انتخابت برس" eyebrow="مرور بر اساس دسته" description="یک مسیر را انتخاب کن؛ فهرست همان لحظه برایت مرتب می‌شود." href="/movies" link-label="همه محتوا" dark />
        <CategoryChips v-model="activeCategory" :items="categoryOptions" />
      </div>
    </section>

    <LazyMovieRow :title="activeCategoryLabel" :eyebrow="`${categoryItems.length} عنوان برای شروع`" :items="categoryItems" href="/movies" dark />

    <section v-if="hasContinue" id="continue" class="content-section">
      <SectionHeader title="ادامه تماشا" eyebrow="از همان‌جا ادامه بده" href="/profile#continue" dark />
      <div class="hide-scrollbar -mx-4 flex snap-x gap-3.5 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-2 sm:gap-4 sm:overflow-visible sm:px-0 xl:grid-cols-4">
        <ContinueWatchingCard v-for="item in continueWatching" :key="item.id" :item="item" class="w-[88%] shrink-0 snap-start sm:w-auto" />
      </div>
    </section>

    <LazyMovieRow id="recommended" title="پیشنهادهای مخصوص تو" :eyebrow="recommendationEyebrow" :description="isPersonalized ? 'بر اساس انتخاب‌ها و تماشاهای اخیر تو مرتب شده است.' : 'برای شروع، از میان عنوان‌های محبوب و خوش‌امتیاز انتخاب کرده‌ایم.'" :items="recommended" href="/movies" dark show-reasons />
    <LazyMovieRow title="ترند امروز" eyebrow="پرگفت‌وگو و پرتماشا" :items="trending" href="/movies?sort=trending" dark />

    <section class="content-section" aria-labelledby="watch-party-home-title">
      <div class="cinema-panel relative isolate overflow-hidden rounded-3xl border border-crimson/20 p-5 sm:p-7">
        <span class="pointer-events-none absolute -left-16 -top-20 -z-10 size-56 rounded-full bg-crimson/15 blur-3xl" aria-hidden="true" />
        <div class="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex items-start gap-4">
            <span class="grid size-12 shrink-0 place-items-center rounded-2xl bg-wine text-crimson-hover ring-1 ring-crimson/25"><CinematicIcon name="users" class="size-6" /></span>
            <div><p class="text-[11px] font-black text-crimson-hover">هم‌زمان، حتی از راه دور</p><h2 id="watch-party-home-title" class="mt-1 text-xl font-black text-ink sm:text-2xl">با دوستانت تماشا کن</h2><p class="mt-2 max-w-2xl text-sm leading-7 text-secondary">یک اتاق خصوصی بساز؛ پخش و گفت‌وگو برای همه اعضا زنده و هماهنگ می‌ماند.</p></div>
          </div>
          <NuxtLink to="/watch-party" class="action-primary w-full shrink-0 sm:w-auto"><CinematicIcon name="users" class="size-5" />ساخت اتاق تماشا</NuxtLink>
        </div>
      </div>
    </section>

    <DeferredContent id="mood" class="scroll-mt-24" min-height="28rem">
      <LazyMoodDiscovery v-model="activeMood" />
      <LazyMovieRow v-if="activeMood" title="هماهنگ با حال امشب" :eyebrow="`${moodItems.length} پیشنهاد پیدا شد`" :items="moodItems" dark show-reasons />
    </DeferredContent>

    <DeferredContent v-if="weeklyFeatured" min-height="31rem"><LazyFeaturedBanner :item="weeklyFeatured" /></DeferredContent>
    <DeferredContent><LazyMovieRow title="تازه اضافه شده‌ها" eyebrow="همین حالا در کاتالوگ" :items="newReleases" href="/movies?sort=newest" dark /></DeferredContent>
    <DeferredContent v-if="dubbed.length"><LazyMovieRow title="دوبله فارسی" eyebrow="تماشای راحت‌تر با صدای فارسی" :items="dubbed" href="/movies?availability=dubbed" dark /></DeferredContent>
    <DeferredContent v-if="recommendedSeries.length"><LazyMovieRow title="سریال‌های پیشنهادی" eyebrow="داستان‌هایی برای چند شب" :items="recommendedSeries" href="/series" dark show-reasons /></DeferredContent>
    <DeferredContent v-if="familyAnimation.length"><LazyMovieRow title="انیمیشن و خانوادگی" eyebrow="برای تماشای جمعی" :items="familyAnimation" href="/movies?format=animation" dark /></DeferredContent>

    <DeferredContent min-height="24rem">
      <section class="content-section render-later">
        <SectionHeader title="کالکشن‌های دست‌چین‌شده" eyebrow="برای وقتی که یک ژانر کافی نیست" description="چند مسیر داستانی با ریتم و حال‌وهوای مشخص." dark />
        <div class="grid gap-4 md:grid-cols-3"><LazyCollectionCard v-for="collection in collections" :key="collection.title" v-bind="collection" /></div>
      </section>
    </DeferredContent>
  </div>
</template>
