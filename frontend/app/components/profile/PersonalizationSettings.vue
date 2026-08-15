<script setup lang="ts">
const authStore = useAuthStore()
const { genres } = useCatalog()
const {
  personalizationEnabled,
  preferences,
  setPersonalizationEnabled,
  updatePreferences,
} = useAnalyticsEvent()
const { ensureAccountPersonalization } = usePersonalizationState()
const {
  rankedRecommendations,
  recommendationsPending,
  recommendationsError,
  refreshRecommendations,
  tasteSummary,
} = usePersonalizedRecommendations(4)

const showManual = ref(false)

const playbackOptions = [
  { value: 'any' as const, label: 'فرقی ندارد' },
  { value: 'dubbed' as const, label: 'دوبله فارسی' },
  { value: 'subtitle' as const, label: 'زیرنویس' },
  { value: 'original' as const, label: 'زبان اصلی' },
]

const genreChoices = computed(() => genres.value.slice(0, 16))
const detectedGenres = computed(() => tasteSummary.value?.top_genres || [])

function toggleFavoriteGenre(slug: string) {
  const current = new Set(preferences.value.favorite_genres)
  if (current.has(slug)) current.delete(slug)
  else current.add(slug)
  updatePreferences({
    favorite_genres: [...current].slice(0, 12),
    disliked_genres: preferences.value.disliked_genres.filter(item => item !== slug),
  })
}

function setPlayback(value: typeof playbackOptions[number]['value']) {
  updatePreferences({ playback_preference: value })
}

onMounted(() => {
  ensureAccountPersonalization()
  if (authStore.isAuthenticated) refreshRecommendations()
})
</script>

<template>
  <section id="personalization" class="content-section scroll-under-header" aria-labelledby="personalization-title">
    <div class="overflow-hidden rounded-2xl bg-surface ring-1 ring-line sm:rounded-3xl">
      <div class="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:p-7">
        <div class="min-w-0">
          <p class="text-xs font-black text-primary-300">پیشنهادهای تو</p>
          <h2 id="personalization-title" class="mt-1 text-lg font-black text-ink sm:text-2xl">مخصوص حساب {{ authStore.user?.username || 'تو' }}</h2>
          <div v-if="detectedGenres.length" class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="genre in detectedGenres"
              :key="genre.slug"
              class="inline-flex min-h-9 items-center rounded-xl bg-primary-500/12 px-3 text-[11px] font-bold text-brand ring-1 ring-primary-500/25"
            >
              {{ genre.title }}
            </span>
          </div>
        </div>

        <div class="flex shrink-0 items-center justify-between gap-4 rounded-2xl bg-canvas p-3.5 ring-1 ring-line sm:min-w-52">
          <p class="text-sm font-black text-ink">{{ personalizationEnabled ? 'فعال' : 'خاموش' }}</p>
          <button
            type="button"
            role="switch"
            :aria-checked="personalizationEnabled"
            aria-label="روشن یا خاموش کردن پیشنهادهای شخصی"
            class="relative h-11 w-14 shrink-0 rounded-full ring-1 ring-inset transition"
            :class="personalizationEnabled ? 'bg-primary-500 ring-primary-400' : 'bg-elevated ring-line'"
            @click="setPersonalizationEnabled(!personalizationEnabled)"
          >
            <span class="absolute top-2 h-7 w-7 rounded-full bg-ink shadow-sm transition" :class="personalizationEnabled ? 'left-1.5' : 'left-6'" />
          </button>
        </div>
      </div>

      <div v-if="personalizationEnabled" class="border-t border-line bg-canvas-soft p-4 sm:p-7">
        <section aria-labelledby="recommendation-preview-title">
          <h3 id="recommendation-preview-title" class="text-base font-black text-ink sm:text-lg">پیشنهادهای فعلی</h3>

          <div v-if="recommendationsPending" class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="در حال بارگذاری">
            <div v-for="index in 4" :key="index" class="skeleton-card h-28" />
          </div>
          <div v-else-if="rankedRecommendations.length" class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <NuxtLink
              v-for="entry in rankedRecommendations"
              :key="`${entry.item.type}-${entry.item.id}`"
              :to="`/${entry.item.type === 'movie' ? 'movies' : 'series'}/${entry.item.slug}`"
              no-prefetch
              class="group flex min-w-0 gap-3 rounded-2xl bg-elevated p-2.5 ring-1 ring-line transition hover:bg-primary-500/10 hover:ring-primary-500/40"
            >
              <NuxtImg :src="entry.item.poster_url" :alt="`پوستر ${entry.item.title}`" class="aspect-[2/3] w-14 shrink-0 rounded-xl object-cover" loading="lazy" />
              <span class="min-w-0 py-1">
                <strong class="block truncate text-xs font-black text-ink">{{ entry.item.title }}</strong>
                <span class="mt-1 line-clamp-2 block text-[10px] leading-5 text-primary-300">{{ entry.reasons[0] }}</span>
              </span>
            </NuxtLink>
          </div>
          <div v-else class="mt-4 rounded-2xl bg-elevated p-4 text-center ring-1 ring-line">
            <p class="text-xs font-bold text-secondary">{{ recommendationsError ? 'الان پیشنهادها در دسترس نیست.' : 'با کمی تماشا، اینجا پر می‌شود.' }}</p>
            <button v-if="recommendationsError" type="button" class="ui-ghost-button mt-2 min-h-11 text-xs" @click="refreshRecommendations()">تلاش دوباره</button>
          </div>
        </section>

        <div class="mt-5">
          <button
            type="button"
            class="inline-flex min-h-11 items-center gap-2 rounded-xl bg-elevated px-3 text-xs font-bold text-secondary ring-1 ring-line transition hover:text-ink"
            :aria-expanded="showManual"
            @click="showManual = !showManual"
          >
            <CinematicIcon name="sliders" class="size-4" />
            {{ showManual ? 'بستن تنظیمات' : 'تنظیمات بیشتر' }}
          </button>

          <section v-if="showManual" class="mt-3 rounded-2xl bg-canvas p-4 text-ink ring-1 ring-line sm:rounded-3xl sm:p-5" aria-labelledby="taste-prefs-title">
            <h3 id="taste-prefs-title" class="text-base font-black sm:text-lg">ژانر و شیوه پخش</h3>

            <div class="mt-4 flex flex-wrap gap-2" role="group" aria-label="ژانرهای مورد علاقه">
              <button
                v-for="genre in genreChoices"
                :key="genre.slug"
                type="button"
                class="inline-flex min-h-10 items-center rounded-xl px-3 text-[11px] font-bold ring-1 transition"
                :class="preferences.favorite_genres.includes(genre.slug) ? 'bg-primary-500/15 text-brand ring-primary-500/30' : 'bg-elevated text-secondary ring-line hover:text-ink'"
                :aria-pressed="preferences.favorite_genres.includes(genre.slug)"
                @click="toggleFavoriteGenre(genre.slug)"
              >
                {{ genre.title }}
              </button>
            </div>

            <div class="mt-4 flex flex-wrap gap-2" role="group" aria-label="ترجیح پخش">
              <button
                v-for="option in playbackOptions"
                :key="option.value"
                type="button"
                class="inline-flex min-h-10 items-center rounded-xl px-3 text-[11px] font-bold ring-1 transition"
                :class="preferences.playback_preference === option.value ? 'bg-primary-500 text-night-950 ring-primary-400' : 'bg-elevated text-secondary ring-line hover:text-ink'"
                :aria-pressed="preferences.playback_preference === option.value"
                @click="setPlayback(option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  </section>
</template>
