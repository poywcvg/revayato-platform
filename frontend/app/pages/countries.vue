<script setup lang="ts">
import {
  catalogCountries,
  countryRegions,
  localizeCountry,
  regionForCountryCode,
  type CatalogCountry,
  type CountryRegionId,
} from '~/data/countries'

interface ApiCountry {
  id: number
  name: string
  code: string
  movie_count?: number
  series_count?: number
}

const { api } = useApi()
const { data, pending } = await useAsyncData(
  'catalog-countries-page',
  () => api<ApiCountry[]>('/countries/'),
  { default: () => [] },
)

const query = ref('')
const activeRegion = ref<CountryRegionId | 'all'>('all')

const countries = computed<CatalogCountry[]>(() => {
  const source = data.value.length
    ? data.value.map(country => ({
        code: country.code.toUpperCase(),
        name: localizeCountry(country.name, country.code),
        movie_count: Number(country.movie_count || 0),
        series_count: Number(country.series_count || 0),
      }))
    : catalogCountries.map(country => ({ ...country, movie_count: 0, series_count: 0 }))

  return [...new Map(source.map(country => [country.code, country])).values()]
    .filter(country => (country.movie_count || 0) + (country.series_count || 0) > 0 || !data.value.length)
    .sort((a, b) => {
      const scoreDiff = ((b.movie_count || 0) + (b.series_count || 0)) - ((a.movie_count || 0) + (a.series_count || 0))
      if (scoreDiff) return scoreDiff
      return a.name.localeCompare(b.name, 'fa')
    })
})

const featuredCountries = computed(() => countries.value.slice(0, 10))

const filteredCountries = computed(() => {
  const needle = query.value
    .trim()
    .replace(/[يى]/g, 'ی')
    .replace(/ك/g, 'ک')
    .toLowerCase()

  return countries.value.filter((country) => {
    if (activeRegion.value !== 'all' && regionForCountryCode(country.code) !== activeRegion.value) {
      return false
    }
    if (!needle) return true
    return country.name.replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').toLowerCase().includes(needle)
      || country.code.toLowerCase().includes(needle)
  })
})

const groupedCountries = computed(() =>
  countryRegions
    .map(region => ({
      ...region,
      items: filteredCountries.value.filter(country => regionForCountryCode(country.code) === region.id),
    }))
    .filter(region => region.items.length > 0),
)

const regionFilters = computed(() => [
  { id: 'all' as const, label: 'همه', count: countries.value.length },
  ...countryRegions.map(region => ({
    id: region.id,
    label: region.label,
    count: countries.value.filter(country => regionForCountryCode(country.code) === region.id).length,
  })).filter(region => region.count > 0),
])

const totalMovies = computed(() => countries.value.reduce((sum, country) => sum + (country.movie_count || 0), 0))
const totalSeries = computed(() => countries.value.reduce((sum, country) => sum + (country.series_count || 0), 0))

function titleCount(country: CatalogCountry) {
  return (country.movie_count || 0) + (country.series_count || 0)
}

useSeoMeta({
  title: 'فیلم و سریال بر اساس کشور',
  description: 'سینمای کشورهای موجود در کاتالوگ روایتو را ببینید و مستقیم به فیلم‌ها و سریال‌های همان کشور بروید.',
})
</script>

<template>
  <div class="countries-page page-section pb-14">
    <header class="countries-hero">
      <div class="countries-hero__glow" aria-hidden="true" />
      <div class="countries-hero__grid" aria-hidden="true" />

      <div class="countries-hero__content">
        <div class="countries-hero__copy">
          <span class="countries-hero__icon" aria-hidden="true">
            <CinematicIcon name="globe" class="size-5" />
          </span>
          <div class="min-w-0">
            <p class="countries-hero__eyebrow">همگام با کاتالوگ</p>
            <h1 class="countries-hero__title">کشورها</h1>
            <p class="countries-hero__desc">
              فقط کشورهایی که در فیلم‌ها و سریال‌های منتشرشده روایتو حضور دارند؛ با شمارش واقعی و لینک مستقیم به همان فیلتر.
            </p>
          </div>
        </div>

        <div class="countries-hero__meta" aria-live="polite">
          <span class="countries-hero__stat">
            <strong class="tabular-nums">{{ countries.length.toLocaleString('fa-IR') }}</strong>
            کشور فعال
          </span>
          <span class="countries-hero__stat countries-hero__stat--muted">
            <strong class="tabular-nums">{{ totalMovies.toLocaleString('fa-IR') }}</strong>
            فیلم
          </span>
          <span class="countries-hero__stat countries-hero__stat--muted">
            <strong class="tabular-nums">{{ totalSeries.toLocaleString('fa-IR') }}</strong>
            سریال
          </span>
        </div>
      </div>

      <div class="countries-hero__tools">
        <label class="countries-search">
          <CinematicIcon name="search" class="size-4 shrink-0 text-muted" />
          <input
            v-model="query"
            type="search"
            enterkeyhint="search"
            autocomplete="off"
            class="countries-search__input"
            placeholder="جستجوی نام کشور..."
            aria-label="جستجوی کشور"
          >
          <button
            v-if="query"
            type="button"
            class="countries-search__clear"
            aria-label="پاک کردن جستجو"
            @click="query = ''"
          >
            <CinematicIcon name="x" class="size-3.5" />
          </button>
        </label>

        <div class="countries-regions" role="tablist" aria-label="فیلتر منطقه">
          <button
            v-for="region in regionFilters"
            :key="region.id"
            type="button"
            role="tab"
            class="countries-regions__chip"
            :class="activeRegion === region.id && 'countries-regions__chip--active'"
            :aria-selected="activeRegion === region.id"
            @click="activeRegion = region.id"
          >
            <span class="truncate">{{ region.label }}</span>
            <span class="countries-regions__count tabular-nums">{{ region.count.toLocaleString('fa-IR') }}</span>
          </button>
        </div>
      </div>
    </header>

    <section
      v-if="featuredCountries.length && activeRegion === 'all' && !query"
      class="countries-featured"
      aria-labelledby="countries-featured-title"
    >
      <div class="countries-section-head">
        <h2 id="countries-featured-title">پرتعدادترین کشورها</h2>
        <p>بر اساس تعداد فیلم و سریال منتشرشده در کاتالوگ.</p>
      </div>

      <div class="countries-featured__row">
        <NuxtLink
          v-for="country in featuredCountries"
          :key="`featured-${country.code}`"
          :to="{ path: '/movies', query: { country: country.code } }"
          class="countries-featured__card"
        >
          <div class="countries-featured__top">
            <CountryFlag :code="country.code" :title="country.name" size="md" />
            <span class="countries-featured__total tabular-nums">{{ titleCount(country).toLocaleString('fa-IR') }}</span>
          </div>
          <span class="countries-featured__name">{{ country.name }}</span>
          <span class="countries-featured__meta">
            {{ (country.movie_count || 0).toLocaleString('fa-IR') }} فیلم ·
            {{ (country.series_count || 0).toLocaleString('fa-IR') }} سریال
          </span>
        </NuxtLink>
      </div>
    </section>

    <div v-if="pending && !countries.length" class="country-grid mt-8">
      <div v-for="index in 12" :key="index" class="skeleton-card h-28 rounded-2xl" />
    </div>

    <div
      v-else-if="!filteredCountries.length"
      class="countries-empty"
      role="status"
    >
      <CinematicIcon name="globe" class="size-7 text-muted" />
      <p>کشوری با این فیلتر در کاتالوگ پیدا نشد.</p>
      <button type="button" class="countries-empty__reset" @click="query = ''; activeRegion = 'all'">
        پاک کردن فیلترها
      </button>
    </div>

    <section
      v-for="region in groupedCountries"
      :key="region.id"
      class="countries-region"
      :aria-labelledby="`countries-region-${region.id}`"
    >
      <div class="countries-section-head">
        <h2 :id="`countries-region-${region.id}`">{{ region.label }}</h2>
        <p>{{ region.items.length.toLocaleString('fa-IR') }} کشور</p>
      </div>

      <div class="countries-list">
        <article
          v-for="country in region.items"
          :key="country.code"
          class="countries-card"
        >
          <div class="countries-card__main">
            <CountryFlag :code="country.code" :title="country.name" size="lg" />
            <div class="min-w-0">
              <h3 class="countries-card__name">{{ country.name }}</h3>
              <p class="countries-card__stats">
                <span class="tabular-nums">{{ (country.movie_count || 0).toLocaleString('fa-IR') }}</span> فیلم
                <span aria-hidden="true">·</span>
                <span class="tabular-nums">{{ (country.series_count || 0).toLocaleString('fa-IR') }}</span> سریال
              </p>
            </div>
          </div>

          <div class="countries-card__actions">
            <NuxtLink
              :to="{ path: '/movies', query: { country: country.code } }"
              class="countries-card__link"
              :class="!(country.movie_count) && 'countries-card__link--disabled'"
              :aria-disabled="!(country.movie_count) ? 'true' : undefined"
              @click="!(country.movie_count) && $event.preventDefault()"
            >
              <CinematicIcon name="movie" class="size-3.5" />
              فیلم‌ها
              <span class="tabular-nums opacity-70">{{ (country.movie_count || 0).toLocaleString('fa-IR') }}</span>
            </NuxtLink>
            <NuxtLink
              :to="{ path: '/series', query: { country: country.code } }"
              class="countries-card__link countries-card__link--ghost"
              :class="!(country.series_count) && 'countries-card__link--disabled'"
              :aria-disabled="!(country.series_count) ? 'true' : undefined"
              @click="!(country.series_count) && $event.preventDefault()"
            >
              <CinematicIcon name="series" class="size-3.5" />
              سریال‌ها
              <span class="tabular-nums opacity-70">{{ (country.series_count || 0).toLocaleString('fa-IR') }}</span>
            </NuxtLink>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.countries-page {
  --countries-ink: var(--theme-text-primary);
  --countries-soft: var(--theme-text-secondary);
  --countries-muted: var(--theme-text-muted);
  --countries-line: color-mix(in srgb, var(--theme-border) 88%, transparent);
  --countries-fill: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
  --countries-surface: color-mix(in srgb, var(--theme-bg-surface) 92%, transparent);
}

.countries-hero {
  position: relative;
  overflow: hidden;
  margin-bottom: 1.75rem;
  border: 1px solid var(--countries-line);
  border-radius: 1.35rem;
  background:
    linear-gradient(160deg, color-mix(in srgb, var(--theme-bg-elevated) 55%, transparent), var(--countries-surface));
  padding: clamp(1.1rem, 2.8vw, 1.75rem);
}

.countries-hero__glow {
  position: absolute;
  inset: auto -20% -45% 20%;
  height: 70%;
  background: radial-gradient(circle, rgb(var(--palette-sand-rgb) / 10%), transparent 68%);
  pointer-events: none;
}

.countries-hero__grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgb(var(--palette-sand-rgb) / 5%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(var(--palette-sand-rgb) / 5%) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(180deg, rgb(0 0 0 / 55%), transparent 88%);
  pointer-events: none;
}

.countries-hero__content {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.countries-hero__copy {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
}

.countries-hero__icon {
  display: grid;
  width: 2.65rem;
  height: 2.65rem;
  flex: none;
  place-items: center;
  border-radius: 0.85rem;
  background: var(--countries-fill);
  color: var(--countries-soft);
  box-shadow: inset 0 0 0 1px var(--countries-line);
}

.countries-hero__eyebrow {
  color: var(--countries-muted);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.countries-hero__title {
  margin-top: 0.2rem;
  color: var(--countries-ink);
  font-size: clamp(1.55rem, 4vw, 2.35rem);
  font-weight: 900;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.countries-hero__desc {
  margin-top: 0.55rem;
  max-width: 38rem;
  color: var(--countries-soft);
  font-size: 0.875rem;
  line-height: 1.8;
}

.countries-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.countries-hero__stat {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 999px;
  background: var(--countries-fill);
  padding: 0.45rem 0.8rem;
  color: var(--countries-ink);
  font-size: 0.7rem;
  font-weight: 800;
  box-shadow: inset 0 0 0 1px var(--countries-line);
}

.countries-hero__stat strong {
  font-weight: 900;
}

.countries-hero__stat--muted {
  color: var(--countries-muted);
}

.countries-hero__tools {
  position: relative;
  display: grid;
  gap: 0.75rem;
  margin-top: 1.15rem;
}

.countries-search {
  display: flex;
  min-height: 2.85rem;
  align-items: center;
  gap: 0.55rem;
  border-radius: 0.9rem;
  background: color-mix(in srgb, var(--theme-bg-main) 55%, var(--theme-bg-elevated));
  padding: 0.35rem 0.7rem 0.35rem 0.85rem;
  box-shadow: inset 0 0 0 1px var(--countries-line);
}

.countries-search__input {
  min-width: 0;
  flex: 1;
  background: transparent;
  color: var(--countries-ink);
  font-size: 0.8125rem;
  font-weight: 700;
  outline: none;
}

.countries-search__input::placeholder {
  color: var(--countries-muted);
}

.countries-search__clear {
  display: grid;
  width: 2rem;
  height: 2rem;
  place-items: center;
  border-radius: 0.55rem;
  color: var(--countries-muted);
}

.countries-search__clear:hover {
  background: var(--countries-fill);
  color: var(--countries-ink);
}

.countries-regions {
  display: flex;
  gap: 0.4rem;
  overflow-x: auto;
  padding-bottom: 0.15rem;
  scrollbar-width: thin;
  -webkit-overflow-scrolling: touch;
}

.countries-regions__chip {
  display: inline-flex;
  min-height: 2.25rem;
  flex: none;
  align-items: center;
  gap: 0.4rem;
  border-radius: 999px;
  background: transparent;
  padding: 0.35rem 0.75rem;
  color: var(--countries-soft);
  font-size: 0.6875rem;
  font-weight: 800;
  box-shadow: inset 0 0 0 1px var(--countries-line);
  transition: color 140ms ease, background-color 140ms ease, box-shadow 140ms ease;
}

.countries-regions__chip:hover {
  background: var(--countries-fill);
  color: var(--countries-ink);
}

.countries-regions__chip--active {
  background: color-mix(in srgb, var(--theme-text-primary) 88%, transparent);
  color: var(--theme-bg-main);
  box-shadow: none;
}

.countries-regions__count {
  opacity: 0.72;
}

.countries-section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.4rem 1rem;
  margin-bottom: 0.85rem;
}

.countries-section-head h2 {
  color: var(--countries-ink);
  font-size: 1rem;
  font-weight: 900;
}

.countries-section-head p {
  color: var(--countries-muted);
  font-size: 0.7rem;
  font-weight: 700;
}

.countries-featured {
  margin-bottom: 1.75rem;
}

.countries-featured__row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 9rem), 1fr));
  gap: 0.55rem;
}

.countries-featured__card {
  display: flex;
  min-height: 5rem;
  flex-direction: column;
  gap: 0.45rem;
  border-radius: 1rem;
  background: var(--countries-surface);
  padding: 0.75rem;
  box-shadow: inset 0 0 0 1px var(--countries-line);
  transition: background-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.countries-featured__card:hover {
  background: var(--countries-fill);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-border-strong) 70%, transparent);
}

.countries-featured__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.countries-featured__total {
  color: var(--countries-muted);
  font-size: 0.6875rem;
  font-weight: 800;
}

.countries-featured__name {
  color: var(--countries-ink);
  font-size: 0.75rem;
  font-weight: 800;
  line-height: 1.4;
}

.countries-featured__meta {
  color: var(--countries-muted);
  font-size: 0.625rem;
  font-weight: 700;
}

.countries-region + .countries-region {
  margin-top: 1.75rem;
}

.countries-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.55rem;
}

.countries-card {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  border-radius: 1rem;
  background: var(--countries-surface);
  padding: 0.9rem;
  box-shadow: inset 0 0 0 1px var(--countries-line);
  transition: box-shadow 160ms ease, transform 160ms ease;
}

.countries-card:focus-within {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-border-strong) 75%, transparent);
}

.countries-card__main {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
}

.countries-card__name {
  color: var(--countries-ink);
  font-size: 0.9375rem;
  font-weight: 900;
  line-height: 1.35;
}

.countries-card__stats {
  margin-top: 0.2rem;
  color: var(--countries-muted);
  font-size: 0.6875rem;
  font-weight: 700;
}

.countries-card__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.4rem;
}

.countries-card__link {
  display: inline-flex;
  min-height: 2.5rem;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  border-radius: 0.7rem;
  background: color-mix(in srgb, var(--theme-text-primary) 90%, transparent);
  color: var(--theme-bg-main);
  font-size: 0.6875rem;
  font-weight: 800;
  transition: opacity 140ms ease, background-color 140ms ease;
}

.countries-card__link:hover {
  opacity: 0.92;
}

.countries-card__link--ghost {
  background: transparent;
  color: var(--countries-soft);
  box-shadow: inset 0 0 0 1px var(--countries-line);
}

.countries-card__link--ghost:hover {
  background: var(--countries-fill);
  color: var(--countries-ink);
  opacity: 1;
}

.countries-card__link--disabled {
  cursor: not-allowed;
  opacity: 0.38;
}

.countries-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.65rem;
  margin-top: 2rem;
  border-radius: 1.15rem;
  background: var(--countries-surface);
  padding: 2.5rem 1rem;
  color: var(--countries-muted);
  font-size: 0.8125rem;
  font-weight: 700;
  box-shadow: inset 0 0 0 1px var(--countries-line);
  text-align: center;
}

.countries-empty__reset {
  margin-top: 0.25rem;
  border-radius: 0.7rem;
  background: var(--countries-fill);
  padding: 0.55rem 0.9rem;
  color: var(--countries-ink);
  font-size: 0.75rem;
  font-weight: 800;
  box-shadow: inset 0 0 0 1px var(--countries-line);
}

@media (min-width: 640px) {
  .countries-hero__content {
    flex-direction: row;
    align-items: flex-end;
    justify-content: space-between;
  }

  .countries-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1024px) {
  .countries-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .countries-card {
    min-height: 100%;
  }
}

@media (hover: hover) and (pointer: fine) {
  .countries-card:hover {
    transform: translate3d(0, -0.1rem, 0);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-border-strong) 70%, transparent);
  }

  .countries-featured__card:hover {
    transform: translate3d(0, -0.1rem, 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .countries-card,
  .countries-featured__card,
  .countries-regions__chip,
  .countries-card__link {
    transition: none;
  }

  .countries-card:hover,
  .countries-featured__card:hover {
    transform: none;
  }
}

:global(html[data-theme="light"] .countries-regions__chip--active) {
  background: color-mix(in srgb, var(--theme-text-primary) 92%, transparent);
  color: #f7f6f2;
}

:global(html[data-theme="light"] .countries-card__link:not(.countries-card__link--ghost)) {
  background: color-mix(in srgb, var(--theme-text-primary) 92%, transparent);
  color: #f7f6f2;
}
</style>
