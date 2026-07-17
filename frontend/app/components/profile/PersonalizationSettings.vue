<script setup lang="ts">
import type { AgeRating, CinematicIconName, ContentSensitivityPreference, PlaybackPreference } from '~/types'

const { catalog, genres } = useCatalog()
const config = useRuntimeConfig()
const serverSyncEnabled = computed(() => config.public.analyticsTransport === 'api')
const {
  consent,
  personalizationEnabled,
  preferences,
  eventCount,
  setPersonalizationEnabled,
  updatePreferences,
  clearLocalPersonalizationData,
} = useAnalyticsEvent()
const { rankedRecommendations } = usePersonalizedRecommendations(4)
const clearConfirmationOpen = ref(false)

const countries = computed(() => [...new Set(catalog.value.flatMap(item => item.country.split(/[،,]/).map(country => country.trim())).filter(Boolean))].slice(0, 8))
const languageOptions = [
  { value: 'fa', label: 'فارسی' },
  { value: 'en', label: 'انگلیسی' },
  { value: 'ko', label: 'کره‌ای' },
  { value: 'fr', label: 'فرانسوی' },
  { value: 'de', label: 'آلمانی' },
  { value: 'tr', label: 'ترکی' },
]
const sensitivityOptions: Array<{ value: ContentSensitivityPreference; title: string; description: string; icon: CinematicIconName }> = [
  { value: 'any', title: 'بدون اولویت', description: 'همه عنوان‌ها با هشدارهای معمول نمایش داده می‌شوند.', icon: 'grid' },
  { value: 'standard', title: 'متعادل', description: 'عنوان‌هایی با هشدار زیاد، کمتر پیشنهاد می‌شوند.', icon: 'sliders' },
  { value: 'reduced', title: 'کم‌حساسیت‌تر', description: 'بیشتر عنوان‌های زیر ۱۸ سال را پیشنهاد بده.', icon: 'shield-check' },
]
const activePreferenceCount = computed(() => preferences.value.favorite_genres.length
  + preferences.value.disliked_genres.length
  + preferences.value.preferred_countries.length
  + preferences.value.preferred_languages.length
  + preferences.value.preferred_age_ratings.length
  + Number(preferences.value.playback_preference !== 'any')
  + Number(preferences.value.content_sensitivity !== 'any'))
const playbackPreference = computed<PlaybackPreference>({
  get: () => preferences.value.playback_preference,
  set: value => updatePreferences({ playback_preference: value }),
})
const playbackPreferenceOptions: Array<{ value: PlaybackPreference; label: string; description: string }> = [
  { value: 'any', label: 'بدون ترجیح', description: 'همه نسخه‌های موجود' },
  { value: 'original', label: 'زبان اصلی', description: 'اولویت با صدای اصلی' },
  { value: 'subtitle', label: 'زیرنویس فارسی', description: 'اولویت با زیرنویس فارسی' },
  { value: 'dubbed', label: 'دوبله فارسی', description: 'اولویت با صدای فارسی' },
]
const contentSensitivity = computed<ContentSensitivityPreference>({
  get: () => preferences.value.content_sensitivity,
  set: value => updatePreferences({ content_sensitivity: value }),
})

function toggled(items: readonly string[], value: string) {
  return items.includes(value) ? items.filter(item => item !== value) : [...items, value]
}

function toggleFavoriteGenre(slug: string) {
  updatePreferences({
    favorite_genres: toggled(preferences.value.favorite_genres, slug),
    disliked_genres: preferences.value.disliked_genres.filter(item => item !== slug),
  })
}

function toggleDislikedGenre(slug: string) {
  updatePreferences({
    disliked_genres: toggled(preferences.value.disliked_genres, slug),
    favorite_genres: preferences.value.favorite_genres.filter(item => item !== slug),
  })
}

function toggleCountry(country: string) {
  updatePreferences({ preferred_countries: toggled(preferences.value.preferred_countries, country) })
}

function toggleLanguage(language: string) {
  updatePreferences({ preferred_languages: toggled(preferences.value.preferred_languages, language) })
}

function toggleAgeRating(rating: AgeRating) {
  updatePreferences({
    preferred_age_ratings: preferences.value.preferred_age_ratings.includes(rating)
      ? preferences.value.preferred_age_ratings.filter(item => item !== rating)
      : [...preferences.value.preferred_age_ratings, rating],
  })
}

function clearPersonalizationData() {
  clearLocalPersonalizationData()
  clearConfirmationOpen.value = false
}
</script>

<template>
  <section id="personalization" class="content-section scroll-mt-24" aria-labelledby="personalization-title">
    <div class="overflow-hidden rounded-3xl bg-surface shadow-xl shadow-black/20 ring-1 ring-line">
      <div class="grid gap-6 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div>
          <div class="flex items-start gap-4">
            <span class="grid size-12 shrink-0 place-items-center rounded-2xl bg-primary-500/14 text-primary-300 ring-1 ring-primary-500/20"><CinematicIcon name="ai" class="size-7" /></span>
            <div>
              <p class="text-xs font-black text-primary-300">انتخاب با توست</p>
              <h2 id="personalization-title" class="mt-1 text-xl font-black text-ink sm:text-2xl">پیشنهادهای شخصی‌سازی‌شده</h2>
              <p class="mt-2 max-w-2xl text-sm leading-7 text-secondary">با کمک تماشاها و جستجوهایت، عنوان‌های نزدیک به سلیقه تو را پیدا می‌کنیم.</p>
            </div>
          </div>

          <div class="mt-5 rounded-2xl bg-elevated p-4 text-sm leading-7 text-secondary ring-1 ring-line">
            <p class="flex items-start gap-2"><CinematicIcon name="shield-check" class="mt-1 size-5 shrink-0 text-success" /><span>فقط وقتی این گزینه را روشن کنی، انتخاب‌هایت در همین سایت برای پیشنهاد بهتر استفاده می‌شوند.</span></p>
            <p class="mt-2 flex items-start gap-2"><CinematicIcon name="eye-off" class="mt-1 size-5 shrink-0 text-muted" /><span>تاریخچه مرورگر و کارهایی که در سایت‌های دیگر انجام می‌دهی بررسی نمی‌شوند.</span></p>
          </div>
        </div>

        <div class="min-w-60 rounded-2xl bg-canvas p-4 text-ink ring-1 ring-line">
          <div class="flex items-center justify-between gap-5">
            <div><p class="text-sm font-black">شخصی‌سازی</p><p class="mt-1 text-xs text-slate-400">{{ personalizationEnabled ? 'فعال روی این دستگاه' : consent === 'unset' ? 'خاموش به‌صورت پیش‌فرض' : 'غیرفعال شده' }}</p></div>
            <button type="button" role="switch" :aria-checked="personalizationEnabled" aria-label="فعال‌سازی پیشنهادهای شخصی‌سازی‌شده" class="relative h-11 w-14 rounded-full ring-1 ring-inset transition" :class="personalizationEnabled ? 'bg-primary-500 ring-primary-400' : 'bg-elevated ring-line'" @click="setPersonalizationEnabled(!personalizationEnabled)"><span class="absolute top-2 h-7 w-7 rounded-full bg-ink shadow-sm transition" :class="personalizationEnabled ? 'left-1.5' : 'left-6'" /></button>
          </div>
          <p class="mt-4 border-t border-white/10 pt-3 text-[11px] leading-5 text-slate-400">هر وقت بخواهی می‌توانی این گزینه را خاموش کنی. با خاموش کردن، سابقه پیشنهادهای روی این دستگاه پاک می‌شود.</p>
        </div>
      </div>

      <div v-if="personalizationEnabled" class="border-t border-line bg-canvas-soft p-5 sm:p-7">
        <div class="grid gap-6 xl:grid-cols-2">
          <fieldset>
            <legend class="text-sm font-black text-ink">ژانرهای موردعلاقه</legend>
            <p class="mt-1 text-xs text-slate-500">این ژانرها بیشتر به تو پیشنهاد می‌شوند.</p>
            <div class="mt-3 flex flex-wrap gap-2"><button v-for="genre in genres" :key="genre.id" type="button" class="rounded-xl px-3 py-2 text-xs font-bold transition" :class="preferences.favorite_genres.includes(genre.slug) ? 'bg-primary-500 text-night-950' : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'" :aria-pressed="preferences.favorite_genres.includes(genre.slug)" @click="toggleFavoriteGenre(genre.slug)">{{ genre.title }}</button></div>
          </fieldset>

          <fieldset>
            <legend class="text-sm font-black text-ink">ژانرهای کمتر موردعلاقه</legend>
            <p class="mt-1 text-xs text-slate-500">این ژانرها حذف نمی‌شوند؛ فقط کمتر پیشنهاد می‌شوند.</p>
            <div class="mt-3 flex flex-wrap gap-2"><button v-for="genre in genres" :key="genre.id" type="button" class="rounded-xl px-3 py-2 text-xs font-bold transition" :class="preferences.disliked_genres.includes(genre.slug) ? 'bg-crimson/20 text-coral-200 ring-1 ring-crimson/40' : 'bg-elevated text-secondary ring-1 ring-line hover:text-coral-200 hover:ring-crimson/40'" :aria-pressed="preferences.disliked_genres.includes(genre.slug)" @click="toggleDislikedGenre(genre.slug)">{{ genre.title }}</button></div>
          </fieldset>

          <fieldset>
            <legend class="text-sm font-black text-ink">کشور و زبان ترجیحی</legend>
            <div class="mt-3 flex flex-wrap gap-2"><button v-for="country in countries" :key="country" type="button" class="rounded-xl px-3 py-2 text-xs font-bold transition" :class="preferences.preferred_countries.includes(country) ? 'bg-primary-500 text-night-950' : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'" :aria-pressed="preferences.preferred_countries.includes(country)" @click="toggleCountry(country)">{{ country }}</button></div>
            <div class="mt-2 flex flex-wrap gap-2"><button v-for="language in languageOptions" :key="language.value" type="button" class="rounded-xl px-3 py-2 text-xs font-bold transition" :class="preferences.preferred_languages.includes(language.value) ? 'bg-primary-500/18 text-primary-200 ring-1 ring-primary-500/35' : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'" :aria-pressed="preferences.preferred_languages.includes(language.value)" @click="toggleLanguage(language.value)">{{ language.label }}</button></div>
          </fieldset>

          <fieldset>
            <legend class="text-sm font-black text-ink">رده سنی ترجیحی</legend>
            <div class="mt-3 flex flex-wrap gap-2"><button v-for="rating in (['12+', '15+', '18+'] as AgeRating[])" :key="rating" type="button" class="rounded-xl px-4 py-2 text-xs font-black transition" :class="preferences.preferred_age_ratings.includes(rating) ? 'bg-primary-500 text-night-950' : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'" :aria-pressed="preferences.preferred_age_ratings.includes(rating)" @click="toggleAgeRating(rating)">{{ rating }}</button></div>
          </fieldset>

          <div class="block"><span class="text-sm font-black text-ink">ترجیح صوت و زیرنویس</span><UiSelect v-model="playbackPreference" :options="playbackPreferenceOptions" label="ترجیح صوت و زیرنویس" icon="audio" class="mt-2" /></div>
          <fieldset class="xl:col-span-2">
            <legend class="text-sm font-black text-ink">حساسیت محتوایی</legend>
            <p class="mt-1 text-xs leading-6 text-slate-500">این گزینه فقط پیشنهادها را جابه‌جا می‌کند و هیچ فیلم یا سریالی را پنهان نمی‌کند.</p>
            <div class="mt-3 grid gap-2 sm:grid-cols-3">
              <button v-for="option in sensitivityOptions" :key="option.value" type="button" class="flex min-h-24 items-start gap-3 rounded-2xl p-3 text-right transition" :class="contentSensitivity === option.value ? 'bg-primary-500/14 text-ink ring-2 ring-primary-500' : 'bg-elevated text-secondary ring-1 ring-line hover:ring-primary-500/40'" :aria-pressed="contentSensitivity === option.value" @click="contentSensitivity = option.value">
                <CinematicIcon :name="option.icon" class="mt-0.5 size-5 shrink-0" :class="contentSensitivity === option.value ? 'text-primary-400' : 'text-slate-500'" />
                <span><strong class="block text-xs font-black">{{ option.title }}</strong><span class="mt-1 block text-[11px] leading-5" :class="contentSensitivity === option.value ? 'text-slate-300' : 'text-slate-500'">{{ option.description }}</span></span>
              </button>
            </div>
          </fieldset>
        </div>

        <section class="mt-6 rounded-3xl bg-canvas p-4 text-ink ring-1 ring-line sm:p-5" aria-labelledby="recommendation-preview-title">
          <div class="flex flex-wrap items-end justify-between gap-3"><div><p class="text-[11px] font-black text-primary-400">نمونه پیشنهادها</p><h3 id="recommendation-preview-title" class="mt-1 text-lg font-black">نتیجه انتخاب‌های فعلی</h3></div><span class="rounded-xl bg-white/5 px-3 py-2 text-[11px] font-bold text-slate-400 ring-1 ring-white/10">{{ activePreferenceCount }} انتخاب ثبت‌شده</span></div>
          <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <NuxtLink v-for="entry in rankedRecommendations" :key="`${entry.item.type}-${entry.item.id}`" :to="`/${entry.item.type === 'movie' ? 'movies' : 'series'}/${entry.item.slug}`" no-prefetch class="group flex min-w-0 gap-3 rounded-2xl bg-white/5 p-2.5 ring-1 ring-white/10 transition hover:bg-white/10 hover:ring-primary-500/40">
              <NuxtImg :src="entry.item.poster_url" :alt="`پوستر ${entry.item.title}`" class="aspect-[2/3] w-14 shrink-0 rounded-xl object-cover" loading="lazy" />
              <span class="min-w-0 py-1"><strong class="block truncate text-xs font-black text-white">{{ entry.item.title }}</strong><span class="mt-1 line-clamp-2 block text-[10px] leading-5 text-primary-300">{{ entry.reasons[0] }}</span><span class="mt-1 block text-[10px] text-slate-500">هماهنگی با سلیقه تو {{ Math.round(entry.score) }}</span></span>
            </NuxtLink>
          </div>
        </section>

        <div class="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
          <p class="text-xs leading-6 text-muted"><strong class="text-secondary">{{ eventCount }}</strong> انتخاب مثل تماشا، جستجو یا امتیاز روی این دستگاه ثبت شده است. {{ serverSyncEnabled ? 'ذخیره در حساب کاربری روشن است.' : 'چیزی خودکار به حساب کاربری فرستاده نمی‌شود.' }}</p>
          <button v-if="!clearConfirmationOpen" type="button" class="ui-destructive-button px-4 py-2.5 text-xs" @click="clearConfirmationOpen = true"><CinematicIcon name="trash" class="size-4" />پاک‌کردن سابقه پیشنهادها</button>
          <div v-else class="flex flex-wrap items-center gap-2 rounded-2xl bg-error/10 p-2 ring-1 ring-error/30"><span class="px-2 text-xs font-bold text-error">همه انتخاب‌ها و سابقه پیشنهادها پاک شوند؟</span><button type="button" class="min-h-10 rounded-xl bg-error px-3 py-2 text-xs font-black text-ink hover:brightness-110" @click="clearPersonalizationData">بله، پاک شود</button><button type="button" class="min-h-10 rounded-xl bg-elevated px-3 py-2 text-xs font-black text-secondary ring-1 ring-line hover:text-ink" @click="clearConfirmationOpen = false">انصراف</button></div>
        </div>
      </div>
    </div>
  </section>
</template>
