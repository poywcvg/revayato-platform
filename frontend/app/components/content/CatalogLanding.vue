<script setup lang="ts">
/**
 * Server-rendered landing page for one slice of the catalog — «فیلم اکشن»,
 * «سریال کره‌ای», «فیلم‌های 2024», «فیلم دوبله فارسی». These are the head
 * queries people type, and the filtered browser (/movies?genre=…) could never
 * rank for them: it is one canonical URL with the list built from the query.
 *
 * Each landing is a real page: its own URL and canonical, an H1 and a factual
 * intro, crawlable <a href> pagination, links to sibling landings, and an
 * ItemList + BreadcrumbList graph. A slice with too few titles is served but
 * kept out of the index (thin content); an unknown one is a 404.
 */
import type { ContentType, Movie } from '~/types'
import type { Crumb } from '~/utils/seo'
import {
  adaptApiCatalogItem,
  type ApiCatalogItem,
  type ApiListResponse,
  unwrapApiList,
} from '~/data/catalogAdapter'
import { countryDemonym, isKnownCountryCode, localizeCountry } from '~/data/countries'
import {
  CATALOG_PAGE_SIZE,
  clampPage,
  offsetFromPage,
  pageFromQuery,
  totalPagesFor,
} from '~/composables/usePagination'

type LandingFacet = 'genre' | 'country' | 'year' | 'dubbed' | 'subtitle'

const props = defineProps<{
  type: ContentType
  facet: LandingFacet
  value?: string
}>()

/** Mirrors MIN_LANDING_TITLES in backend/apps/catalog/sitemap_api.py. */
const MIN_INDEXABLE_TITLES = 8

interface ApiGenre {
  slug: string
  title: string
  movie_count?: number
  series_count?: number
}

const route = useRoute()
const config = useRuntimeConfig()
const { api } = useApi()

const isSeries = props.type === 'series'
const kind = isSeries ? 'سریال' : 'فیلم'
const kindPlural = isSeries ? 'سریال‌ها' : 'فیلم‌ها'
const section = isSeries ? '/series' : '/movies'
const rawValue = String(props.value || '').trim()

// ── Resolve the slice to a name, or 404 ────────────────────────────────────
const { data: genres } = await useAsyncData('landing-genres', () => api<ApiGenre[]>('/genres/'), {
  default: () => [] as ApiGenre[],
})

function genreCount(genre: ApiGenre) {
  return Number((isSeries ? genre.series_count : genre.movie_count) || 0)
}

const currentYear = new Date().getFullYear()
let name = ''
let filter: Record<string, string> = {}
if (props.facet === 'genre') {
  const genre = genres.value.find(entry => entry.slug === rawValue)
  if (genre) {
    name = genre.title
    filter = { genre: genre.slug }
  }
}
else if (props.facet === 'country') {
  const code = rawValue.toUpperCase()
  if (/^[A-Z]{2}$/.test(code) && isKnownCountryCode(code)) {
    name = localizeCountry('', code)
    filter = { country: code }
  }
}
else if (props.facet === 'year') {
  const year = Number(rawValue)
  if (/^\d{4}$/.test(rawValue) && year >= 1900 && year <= currentYear + 3) {
    name = rawValue
    filter = { year: rawValue }
  }
}
else if (props.facet === 'subtitle') {
  name = 'زیرنویس فارسی'
  filter = { availability: 'subtitle' }
}
else {
  name = 'دوبله فارسی'
  filter = { availability: 'dubbed' }
}
if (!name) {
  throw createError({ statusCode: 404, statusMessage: `${kind} پیدا نشد`, fatal: true })
}

// Country codes live lowercase in the URL; anything else is the same page twice.
if (props.facet === 'country' && rawValue !== rawValue.toLowerCase()) {
  await navigateTo({ path: `${section}/country/${rawValue.toLowerCase()}`, query: route.query }, { redirectCode: 301 })
}

// ── Wording ─────────────────────────────────────────────────────────────────
const demonym = props.facet === 'country' ? countryDemonym(rawValue) : ''
/** «فیلم اکشن» / «سریال کره‌ای» / «فیلم‌های ۲۰۲۴» / «فیلم دوبله فارسی» */
const phrase = (() => {
  if (props.facet === 'genre') return `${kind} ${name}`
  if (props.facet === 'country') return demonym ? `${kind} ${demonym}` : `${kindPlural}ی محصول ${name}`
  if (props.facet === 'year') return `${kindPlural}ی ${name}`
  return `${kind} ${name}`
})()
const heading = (() => {
  if (props.facet === 'genre') return `${kindPlural}ی ${name}`
  if (props.facet === 'country') return demonym ? `${kindPlural}ی ${demonym}` : `${kindPlural}ی محصول ${name}`
  if (props.facet === 'year') return `بهترین ${kindPlural}ی سال ${name}`
  return `${kindPlural}ی ${name}`
})()
const eyebrow = props.facet === 'genre'
  ? `ژانر ${name}`
  : props.facet === 'country'
    ? `کشور سازنده: ${name}`
    : props.facet === 'year'
      ? `سال ساخت ${name}`
      : props.facet === 'subtitle' ? 'با زیرنویس فارسی' : 'با صدای فارسی'
const icon = props.facet === 'genre'
  ? 'tag'
  : props.facet === 'country' ? 'globe' : props.facet === 'year' ? 'calendar' : props.facet === 'subtitle' ? 'subtitle' : 'audio'

// ── Titles ──────────────────────────────────────────────────────────────────
const page = computed(() => pageFromQuery(route.query.page))
const { data, pending, error } = await useAsyncData(
  () => `landing-${props.type}-${props.facet}-${rawValue}-${page.value}`,
  async () => {
    const response = await api<ApiListResponse<ApiCatalogItem>>(`${section}/`, {
      query: {
        ...filter,
        // IMDb order covers the whole slice; the engagement-scored sorts only
        // rank a small recent pool and would hide most of the catalog.
        sort: 'rating',
        limit: CATALOG_PAGE_SIZE,
        offset: offsetFromPage(page.value, CATALOG_PAGE_SIZE),
      },
    })
    const mediaBase = String(config.public.mediaCdnBaseUrl)
    const items = unwrapApiList(response).map(item => adaptApiCatalogItem(item, props.type, mediaBase)) as Movie[]
    return { items, count: Array.isArray(response) ? items.length : Number(response.count || items.length) }
  },
  { watch: [page], default: () => ({ items: [] as Movie[], count: 0 }), lazy: import.meta.client },
)

const items = computed(() => data.value?.items || [])
const total = computed(() => data.value?.count || 0)
const totalPages = computed(() => totalPagesFor(total.value, CATALOG_PAGE_SIZE))
const safePage = computed(() => clampPage(page.value, totalPages.value))

// An empty slice, or a page past the end, is not a page: never let it be indexed.
if (import.meta.server && !error.value && (total.value === 0 || page.value > totalPages.value)) {
  throw createError({ statusCode: 404, statusMessage: `${kind}ی در این دسته نیست`, fatal: true })
}

const basePath = computed(() => route.path.replace(/\/+$/, ''))
function pageHref(target: number) {
  return target <= 1 ? basePath.value : `${basePath.value}?page=${target}`
}

const fa = (value: number) => value.toLocaleString('fa-IR')
const intro = computed(() => {
  const count = total.value
  const top = items.value.slice(0, 3).map(item => item.title).filter(Boolean)
  const lead = props.facet === 'dubbed' || props.facet === 'subtitle'
    ? `${fa(count)} ${kind} با ${name} در روایتو منتشر شده است`
    : props.facet === 'year'
      ? `${fa(count)} ${kind} ساخت سال ${name} در روایتو منتشر شده است`
      : props.facet === 'country'
        ? `${fa(count)} ${kind} ساخت ${name} در روایتو منتشر شده است`
        : `${fa(count)} ${kind} در ژانر ${name} در روایتو منتشر شده است`
  const examples = top.length && safePage.value === 1 ? `؛ از جمله ${top.join('، ')}` : ''
  return `${lead}${examples}. فهرست به ترتیب امتیاز IMDb است و صفحه هر عنوان خلاصه داستان، بازیگران و عوامل، امتیازها و — هر جا در دسترس باشد — لینک دانلود و پخش آنلاین با زیرنویس یا دوبله فارسی را دارد.`
})

// ── Links to sibling landings (internal linking = crawl paths + relevance) ──
interface LandingLink { label: string; to: string }
const siblings = computed<LandingLink[]>(() => {
  if (props.facet === 'genre') {
    return genres.value
      .filter(genre => genre.slug !== rawValue && genreCount(genre) >= MIN_INDEXABLE_TITLES)
      .sort((a, b) => genreCount(b) - genreCount(a))
      .slice(0, 14)
      .map(genre => ({ label: `${kind} ${genre.title}`, to: `${section}/genre/${genre.slug}` }))
  }
  if (props.facet === 'year') {
    const year = Number(rawValue)
    return [year + 1, year - 1, year - 2, year - 3]
      .filter(candidate => candidate >= 1900 && candidate <= currentYear + 1)
      .map(candidate => ({ label: `${kindPlural}ی ${candidate}`, to: `${section}/year/${candidate}` }))
  }
  if (props.facet === 'country') {
    return ['US', 'KR', 'TR', 'JP', 'IN', 'GB', 'FR', 'CN', 'ES', 'DE']
      .filter(code => code !== rawValue.toUpperCase())
      .map(code => ({
        label: countryDemonym(code) ? `${kind} ${countryDemonym(code)}` : `${kind} ${localizeCountry('', code)}`,
        to: `${section}/country/${code.toLowerCase()}`,
      }))
  }
  return genres.value
    .filter(genre => genreCount(genre) >= MIN_INDEXABLE_TITLES)
    .sort((a, b) => genreCount(b) - genreCount(a))
    .slice(0, 10)
    .map(genre => ({ label: `${kind} ${genre.title}`, to: `${section}/genre/${genre.slug}` }))
})

const otherKind = computed<LandingLink | null>(() => {
  const otherSection = isSeries ? '/movies' : '/series'
  const otherKindWord = isSeries ? 'فیلم' : 'سریال'
  if (props.facet === 'genre') {
    const genre = genres.value.find(entry => entry.slug === rawValue)
    const count = Number((isSeries ? genre?.movie_count : genre?.series_count) || 0)
    return count >= MIN_INDEXABLE_TITLES ? { label: `${otherKindWord} ${name}`, to: `${otherSection}/genre/${rawValue}` } : null
  }
  const suffix = props.facet === 'dubbed' || props.facet === 'subtitle'
    ? `/${props.facet}`
    : `/${props.facet}/${rawValue.toLowerCase()}`
  const label = props.facet === 'country'
    ? `${otherKindWord} ${demonym || name}`
    : props.facet === 'year' ? `${otherKindWord}\u200cهای ${name}` : `${otherKindWord} ${name}`
  return { label, to: `${otherSection}${suffix}` }
})

const browseHref = computed(() => {
  const query = new URLSearchParams(filter).toString()
  return `${section}${query ? `?${query}` : ''}`
})

// ── Head ────────────────────────────────────────────────────────────────────
const pageSuffix = computed(() => (safePage.value > 1 ? ` — صفحه ${fa(safePage.value)}` : ''))
const seoTitle = computed(() => {
  const base = props.facet === 'year'
    ? `دانلود ${kindPlural}ی ${name} — بهترین ${kindPlural}ی سال ${name}`
    : props.facet === 'dubbed' || props.facet === 'subtitle'
      ? `دانلود ${kind} ${name} — ${kindPlural}ی ${name}`
      : `دانلود ${phrase} — بهترین ${heading} با زیرنویس فارسی`
  return `${base}${pageSuffix.value}`
})
/** «۳٬۳۵۵ فیلم اکشن» / «۴۵۷ فیلم کره‌ای» / «۱۲۰ فیلم سال 2024» / «۶٬۶۲۳ فیلم دوبله فارسی» */
const countedPhrase = computed(() => {
  const count = fa(total.value)
  if (props.facet === 'country') return demonym ? `${count} ${kind} ${demonym}` : `${count} ${kind} محصول ${name}`
  if (props.facet === 'year') return `${count} ${kind} سال ${name}`
  if (props.facet === 'genre') return `${count} ${kind} ${name}`
  return `${count} ${kind} با ${name}`
})
const seoDescription = computed(() => {
  const top = items.value.slice(0, 3).map(item => item.title).filter(Boolean)
  return `دانلود و تماشای آنلاین ${countedPhrase.value} در روایتو${top.length ? `؛ ${top.join('، ')} و…` : '.'} مرتب‌شده بر اساس امتیاز IMDb، با خلاصه داستان، بازیگران و امتیازها.`
})
const canonical = computed(() => absoluteUrl(config.public.siteUrl, pageHref(safePage.value)))

useSeoMeta({
  title: seoTitle,
  description: seoDescription,
  ogTitle: seoTitle,
  ogDescription: seoDescription,
  ogImage: () => items.value.find(item => item.has_backdrop)?.backdrop_url || undefined,
  twitterCard: 'summary_large_image',
  robots: () => (total.value >= MIN_INDEXABLE_TITLES ? 'index, follow, max-image-preview:large' : 'noindex, follow'),
})

const crumbs = computed<Crumb[]>(() => [
  { name: SITE_NAME, path: '/' },
  { name: kindPlural, path: section },
  { name: heading, path: basePath.value },
])

useHead(() => ({
  link: [
    { rel: 'canonical', href: canonical.value },
    ...(safePage.value > 1 ? [{ rel: 'prev', href: absoluteUrl(config.public.siteUrl, pageHref(safePage.value - 1)) }] : []),
    ...(safePage.value < totalPages.value ? [{ rel: 'next', href: absoluteUrl(config.public.siteUrl, pageHref(safePage.value + 1)) }] : []),
  ],
  meta: [{ property: 'og:url', content: canonical.value }],
  script: [{
    key: 'landing-jsonld',
    type: 'application/ld+json',
    innerHTML: jsonLdString({
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'CollectionPage',
          '@id': `${canonical.value}#page`,
          url: canonical.value,
          name: heading,
          description: seoDescription.value,
          inLanguage: 'fa-IR',
          isPartOf: { '@id': `${absoluteUrl(config.public.siteUrl, '/')}#website` },
          mainEntity: {
            '@type': 'ItemList',
            numberOfItems: total.value,
            itemListElement: items.value.map((item, index) => ({
              '@type': 'ListItem',
              position: offsetFromPage(safePage.value, CATALOG_PAGE_SIZE) + index + 1,
              url: absoluteUrl(config.public.siteUrl, detailPath(item)),
              name: item.title,
            })),
          },
        },
        breadcrumbNode(config.public.siteUrl, crumbs.value),
      ],
    }),
  }],
}))
</script>

<template>
  <div class="page-section">
    <nav aria-label="مسیر صفحه" class="mb-3 text-xs font-bold text-muted">
      <ol class="flex flex-wrap items-center gap-1.5">
        <li v-for="(crumb, index) in crumbs" :key="crumb.path" class="flex items-center gap-1.5">
          <NuxtLink
            v-if="index < crumbs.length - 1"
            :to="crumb.path"
            class="transition hover:text-primary-300"
          >
            {{ crumb.name }}
          </NuxtLink>
          <span v-else aria-current="page" class="text-secondary">{{ crumb.name }}</span>
          <CinematicIcon v-if="index < crumbs.length - 1" name="chevron-left" class="size-3.5" aria-hidden="true" />
        </li>
      </ol>
    </nav>

    <PageHero
      :title="heading"
      :eyebrow="eyebrow"
      :description="intro"
      :icon="icon"
      :count="total"
      :count-label="kind"
    >
      <div class="flex flex-wrap gap-2">
        <NuxtLink
          :to="browseHref"
          class="inline-flex min-h-10 items-center gap-2 rounded-xl bg-elevated px-3.5 py-2 text-xs font-bold text-secondary ring-1 ring-line transition hover:text-primary-300 hover:ring-primary-500/40"
        >
          <CinematicIcon name="sliders" class="size-4" />
          فیلتر و مرتب‌سازی بیشتر
        </NuxtLink>
        <NuxtLink
          v-if="otherKind"
          :to="otherKind.to"
          class="inline-flex min-h-10 items-center gap-2 rounded-xl bg-elevated px-3.5 py-2 text-xs font-bold text-secondary ring-1 ring-line transition hover:text-primary-300 hover:ring-primary-500/40"
        >
          <CinematicIcon :name="isSeries ? 'movie' : 'series'" class="size-4" />
          {{ otherKind.label }}
        </NuxtLink>
      </div>
    </PageHero>

    <MovieGrid
      :items="items"
      :loading="pending"
      :empty-title="`${kind}ی در این دسته پیدا نشد`"
      empty-description="به‌زودی عنوان‌های تازه به این دسته اضافه می‌شود."
    />

    <CatalogPagination
      :page="safePage"
      :total-pages="totalPages"
      :total="total"
      :pending="pending"
      :href-for="pageHref"
      :label="`صفحه‌بندی ${heading}`"
    />

    <section v-if="siblings.length" class="mt-8" aria-labelledby="landing-related">
      <h2 id="landing-related" class="mb-3 text-sm font-black text-ink">دسته‌های مرتبط</h2>
      <ul class="flex flex-wrap gap-2">
        <li v-for="link in siblings" :key="link.to">
          <NuxtLink
            :to="link.to"
            class="inline-flex min-h-9 items-center rounded-lg bg-elevated px-3 py-1.5 text-xs font-bold text-secondary ring-1 ring-line transition hover:text-primary-300 hover:ring-primary-500/40"
          >
            {{ link.label }}
          </NuxtLink>
        </li>
      </ul>
    </section>
  </div>
</template>
