<script setup lang="ts">
import type { DownloadLink, Movie } from '~/types'
import type { DownloadPlayRequest } from '~/components/content/DownloadBox.vue'
import { englishCatalogTitle, isMostlyLatin, isMostlyPersian } from '~/utils/displayNames'
import '~/assets/css/media-detail.css'

const props = defineProps<{ item: Movie }>()
const route = useRoute()
const modalOpen = ref(false)
const collectionOpen = ref(false)
const accessModal = ref<'play' | 'download' | null>(route.query.access === 'download' ? 'download' : null)
const requestedMode = ref<'full' | 'trailer'>('full')
const pendingSource = ref('')
const pendingVersion = ref('')
const pendingEpisodeId = ref(0)
const { catalog } = useCatalog()
const authStore = useAuthStore()
const related = useRelatedMovies(() => props.item, 10)
const { isLiked, toggleLike } = useLibrary()
const { trackGenreClick, trackLikeAction, trackTitleView, trackPersonClick, trackTrailerPlay, trackDownload } = useAnalyticsEvent()
const notifications = useNotifications()
const liked = computed(() => isLiked(props.item.id, props.item.type))
const restricted = computed(() => props.item.age_rating === '18+')
const episodeCount = computed(() => props.item.episodes?.length || 0)
const progressPercent = computed(() => Math.min(100, Math.max(0, props.item.progress_percent || 0)))
const primaryGenre = computed(() => props.item.genres[0])
const sameGenreTitles = computed(() => {
  if (!primaryGenre.value) return []
  return catalog.value
    .filter(candidate => candidate.id !== props.item.id && candidate.genres.some(genre => genre.slug === primaryGenre.value?.slug))
    .sort((a, b) => b.rating - a.rating || b.popularity - a.popularity)
    .slice(0, 7)
})
const playLabel = computed(() => props.item.progress_percent > 0 ? 'ادامه تماشا' : 'تماشای آنلاین')
const downloadLinks = computed(() => props.item.download_links || [])

// Hero heading: «دانلود سریال Ted Lasso» over «تد لاسو (2020)».
const kindWord = computed(() => (props.item.type === 'series' ? 'سریال' : 'فیلم'))
const heroEnglish = computed(() => {
  const english = englishCatalogTitle(props.item)
  return isMostlyLatin(english) ? english : ''
})
const heroPersian = computed(() => (
  [props.item.title, props.item.secondary_title, props.item.original_title]
    .map(value => (value || '').trim())
    .find(value => value && isMostlyPersian(value)) || ''
))
const heroGenres = computed(() => props.item.genres.slice(0, 4))
const heroFacts = computed(() => {
  const facts: string[] = []
  if (props.item.type === 'movie' && props.item.duration_minutes) {
    facts.push(`${props.item.duration_minutes.toLocaleString('fa-IR')} دقیقه`)
  }
  if (props.item.type === 'series' && props.item.seasons_count) {
    facts.push(`${props.item.seasons_count.toLocaleString('fa-IR')} فصل`)
  }
  if (props.item.country) facts.push(props.item.country)
  return facts
})

type EpisodeLink = DownloadLink & { season_number: number; episode_number: number }
function isEpisodeLink(link: DownloadLink): link is EpisodeLink {
  return Boolean(link.episode_number)
}
function newestEpisode(links: EpisodeLink[]) {
  return links.reduce<EpisodeLink | null>((best, link) => {
    if (!best) return link
    const a = (link.season_number || 1) * 10000 + link.episode_number
    const b = (best.season_number || 1) * 10000 + best.episode_number
    return a > b ? link : best
  }, null)
}
const twoDigits = (value: number) => value.toLocaleString('fa-IR', { minimumIntegerDigits: 2 })
const episodeLinks = computed(() => downloadLinks.value.filter(isEpisodeLink))
const newestLink = computed(() => newestEpisode(episodeLinks.value))

/** «فصل ۰۴ - قسمت ۰۹ اضافه شد» pills, from the links actually on the page. */
const freshPills = computed(() => {
  const links = downloadLinks.value
  if (props.item.type === 'series') {
    const pills: string[] = []
    const subbed = newestEpisode(episodeLinks.value.filter(link => link.kind !== 'dubbed'))
    const dubbed = newestEpisode(episodeLinks.value.filter(link => link.kind === 'dubbed'))
    if (subbed) pills.push(`فصل ${twoDigits(subbed.season_number || 1)} - قسمت ${twoDigits(subbed.episode_number)} اضافه شد`)
    if (dubbed) pills.push(`دوبله فصل ${twoDigits(dubbed.season_number || 1)} - قسمت ${twoDigits(dubbed.episode_number)} اضافه شد`)
    return pills
  }
  const pills: string[] = []
  if (links.some(link => link.kind === 'dubbed')) pills.push('نسخهٔ دوبله فارسی اضافه شد')
  if (links.some(link => link.kind === 'softsub' || link.kind === 'hardsub')) pills.push('زیرنویس فارسی اضافه شد')
  return pills
})

/** Play the newest episode — subtitled first, dubbed when that is all there is. */
const latestRequest = computed<DownloadPlayRequest | null>(() => {
  const newest = newestLink.value
  if (props.item.type !== 'series' || !newest) return null
  const same = episodeLinks.value.filter(link => (
    (link.season_number || 1) === (newest.season_number || 1) && link.episode_number === newest.episode_number
  ))
  const pick = same.find(link => link.kind === 'softsub')
    || same.find(link => link.kind !== 'dubbed')
    || same[0]
  if (!pick) return null
  return {
    url: pick.url,
    kind: pick.kind === 'dubbed' ? 'dub' : pick.kind === 'softsub' ? 'softsub' : 'original',
    seasonNumber: pick.season_number || 1,
    episodeNumber: pick.episode_number,
  }
})

function playLatest() {
  if (latestRequest.value) requestPlay('full', latestRequest.value)
}
const primaryStreamUrl = computed(() => (
  downloadLinks.value[0]?.url
  || props.item.hls_url
  || props.item.playback?.hls_url
  || props.item.playback?.signed_playback_url
  || ''
))
const canWatchOnline = computed(() => Boolean(primaryStreamUrl.value))
const trailerUrl = computed(() => {
  const url = props.item.trailer_url?.trim() || ''
  return /^https?:\/\//i.test(url) || url.startsWith('/') ? url : ''
})
const hasTrailer = computed(() => Boolean(trailerUrl.value))
const hasDirector = computed(() => Boolean(props.item.crew.length || props.item.director?.trim()))
const qualityBadge = computed(() => props.item.quality || props.item.download_qualities?.[0] || '')
const colorSource = computed(() => props.item.poster_url || props.item.backdrop_url)
const { styleVars } = useDominantColor(colorSource)

const activeSection = ref('story')
const detailTabs = computed(() => [
  { id: 'story', label: 'داستان' },
  ...(downloadLinks.value.length ? [{ id: 'download', label: 'دانلود' }] : []),
  { id: 'info', label: 'اطلاعات' },
  { id: 'cast', label: 'بازیگران' },
  { id: 'comments', label: 'دیدگاه‌ها', count: reviews.value.length },
  ...(related.value.length ? [{ id: 'similar', label: 'آثار مشابه' }] : []),
  ...(authStore.isAuthenticated ? [{ id: 'why-recommended', label: 'چرا پیشنهاد شده؟' }] : []),
])

let sectionObserver: IntersectionObserver | undefined

const { api } = useApi()
const reviews = ref<Array<{
  id?: number
  name: string
  score: number
  text: string
  isSpoiler?: boolean
  createdAt?: string
  adminReply?: string
  adminReplyBy?: string
  adminReplyAt?: string
  isFeatured?: boolean
}>>([])
const myRating = ref<import('~/types').Rating | null>(null)

async function loadReviews() {
  try {
    const summary = await api<{
      reviews?: Array<{
        id: number
        username: string
        score: string
        review: string
        is_spoiler?: boolean
        created_at?: string
        admin_reply?: string
        admin_reply_by_name?: string
        admin_reply_at?: string
        is_featured?: boolean
      }>
      my_rating?: import('~/types').Rating | null
    }>('/engagement/ratings/summary/', {
      query: { content_type: props.item.type, object_id: props.item.id },
    })
    myRating.value = summary.my_rating || null
    reviews.value = (summary.reviews || [])
      .filter(item => item.review?.trim())
      .map(item => ({
        id: item.id,
        name: item.username,
        score: Number(item.score),
        text: item.review,
        isSpoiler: Boolean(item.is_spoiler),
        createdAt: item.created_at,
        adminReply: item.admin_reply || '',
        adminReplyBy: item.admin_reply_by_name || '',
        adminReplyAt: item.admin_reply_at || '',
        isFeatured: Boolean(item.is_featured),
      }))
  } catch {
    reviews.value = []
    myRating.value = null
  }
}

function watchPath(confirmed = false) {
  const query = new URLSearchParams({ mode: requestedMode.value, type: props.item.type, player: '1' })
  if (confirmed) query.set('confirmed', '1')
  if (pendingSource.value) query.set('source', pendingSource.value)
  if (pendingVersion.value) query.set('version', pendingVersion.value)
  if (pendingEpisodeId.value) query.set('episode', String(pendingEpisodeId.value))
  return `/watch/${props.item.slug}?${query.toString()}`
}

function episodeIdFor(seasonNumber: number | null, episodeNumber: number | null) {
  if (!episodeNumber) return 0
  const season = seasonNumber ?? 1
  const match = (props.item.episodes || []).find(episode => (
    (episode.season_number || 1) === season && episode.episode_number === episodeNumber
  ))
  return match?.id || 0
}

function requestPlay(mode: 'full' | 'trailer', request: DownloadPlayRequest | string = '') {
  requestedMode.value = mode
  const normalized: DownloadPlayRequest | null = typeof request === 'string'
    ? (request ? { url: request, kind: 'original', seasonNumber: null, episodeNumber: null } : null)
    : request
  pendingSource.value = normalized?.url || ''
  pendingVersion.value = normalized && normalized.url ? normalized.kind : ''
  pendingEpisodeId.value = normalized ? episodeIdFor(normalized.seasonNumber, normalized.episodeNumber) : 0
  if (restricted.value) modalOpen.value = true
  else if (mode === 'trailer') openTrailer()
  else void navigateTo(watchPath(false))
}

function openPlayOptions() {
  if (downloadLinks.value.length) {
    accessModal.value = 'play'
    return
  }
  requestPlay('full', primaryStreamUrl.value)
}

function openDownloadOptions() {
  if (downloadLinks.value.length) accessModal.value = 'download'
}

function playSelectedVersion(request: DownloadPlayRequest) {
  accessModal.value = null
  requestPlay('full', request)
}

function confirmPlay() {
  modalOpen.value = false
  if (requestedMode.value === 'trailer') openTrailer()
  else void navigateTo(watchPath(true))
  pendingSource.value = ''
  pendingVersion.value = ''
  pendingEpisodeId.value = 0
}

function openTrailer() {
  const url = trailerUrl.value
  if (!url || !import.meta.client) return
  trackTrailerPlay(props.item)
  window.open(url, '_blank', 'noopener,noreferrer')
}

async function toggleLiked() {
  const previous = liked.value
  try {
    const nextLiked = await toggleLike(props.item.id, props.item.type)
    if (nextLiked !== previous) trackLikeAction(props.item, nextLiked)
  } catch {
    // Notification handled by ActionButtons-style callers; keep silent here for hero control.
  }
}

function activateSection(id: string) {
  activeSection.value = id
}

async function shareTitle() {
  if (!import.meta.client) return
  const url = window.location.href
  const title = props.item.title
  try {
    if (navigator.share) {
      await navigator.share({ title, url, text: props.item.description?.slice(0, 120) || title })
      return
    }
    await navigator.clipboard.writeText(url)
    notifications.success('لینک کپی شد', 'می‌توانی لینک این عنوان را برای دیگران بفرستی.')
  } catch {
    // User cancelled share sheet — ignore.
  }
}

function openCollectionModal() {
  if (!authStore.isAuthenticated) {
    void navigateTo({ path: '/auth/login', query: { redirect: route.fullPath } })
    return
  }
  collectionOpen.value = true
}

function startWatchParty() {
  void navigateTo({
    path: '/watch-party',
    query: {
      type: props.item.type,
      id: String(props.item.id),
      slug: props.item.slug,
      title: props.item.title,
    },
  })
}

async function observeDetailSections() {
  if (!import.meta.client) return
  await nextTick()
  sectionObserver?.disconnect()
  const sections = detailTabs.value
    .map(tab => document.getElementById(tab.id))
    .filter((section): section is HTMLElement => Boolean(section))
  if (!sections.length) return

  const hash = window.location.hash.slice(1)
  if (sections.some(section => section.id === hash)) activeSection.value = hash

  sectionObserver = new IntersectionObserver((entries) => {
    const visible = entries
      .filter(entry => entry.isIntersecting)
      .sort((a, b) => Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top))
    const current = visible[0]?.target as HTMLElement | undefined
    if (current) activeSection.value = current.id
  }, { rootMargin: '-96px 0px -62% 0px', threshold: [0, 0.05] })
  sections.forEach(section => sectionObserver?.observe(section))
}

onMounted(() => {
  trackTitleView(props.item)
  void loadReviews()
  void observeDetailSections()
})
watch(() => props.item.id, () => {
  accessModal.value = null
  void loadReviews()
})
watch(() => detailTabs.value.map(tab => tab.id).join('|'), () => { void observeDetailSections() })
onBeforeUnmount(() => sectionObserver?.disconnect())
</script>

<template>
  <article class="media-detail" :style="styleVars">
    <MediaHero
      :backdrop-src="item.backdrop_url || item.poster_url"
      :backdrop-alt="`تصویر زمینه ${item.title}`"
    >
      <BreadcrumbsB
        class="media-hero__crumb"
        size="small"
        :items="[
          { slug: 'home', title: 'خانه', href: '/', icon: 'home' },
          { slug: item.type, title: item.type === 'movie' ? 'فیلم‌ها' : 'سریال‌ها', href: item.type === 'movie' ? '/movies' : '/series' },
          { slug: item.slug, title: item.title, active: true },
        ]"
      />

      <div class="media-hero__layout">
        <MediaPoster
          class="media-hero__poster"
          :src="item.poster_url"
          :alt="`پوستر ${item.title}`"
          :progress-percent="progressPercent"
          :quality-label="qualityBadge"
          :can-play="canWatchOnline"
          :has-trailer="hasTrailer"
          :has-subtitle="item.has_subtitle"
          :is-dubbed="item.is_dubbed"
          @play="openPlayOptions"
          @trailer="requestPlay('trailer')"
        />

        <!-- Both names in the one H1: people search «تلقین» and «Inception» alike. -->
        <div class="media-hero__head">
          <h1 class="media-summary__heading">
            <span class="media-summary__title">
              دانلود {{ kindWord }}
              <bdi v-if="heroEnglish" dir="ltr">{{ heroEnglish }}</bdi>
              <template v-else>{{ item.title }}</template>
            </span>
            <span v-if="heroPersian || item.year" class="media-summary__original">
              <template v-if="heroEnglish && heroPersian">{{ heroPersian }}</template>
              <bdi v-if="item.year" dir="ltr">({{ item.year }})</bdi>
            </span>
          </h1>

          <p v-if="heroGenres.length" class="media-summary__genres">
            <span class="media-summary__label">ژانر:</span>
            <template v-for="(genre, index) in heroGenres" :key="genre.id">
              <NuxtLink
                :to="`${item.type === 'movie' ? '/movies' : '/series'}/genre/${genre.slug}`"
                @click="trackGenreClick(genre.slug)"
              >
                {{ genre.title }}
              </NuxtLink><span v-if="index < heroGenres.length - 1">، </span>
            </template>
          </p>

          <div v-if="heroFacts.length || item.age_rating" class="media-summary__facts">
            <AgeRatingBadge :rating="item.age_rating" />
            <span v-for="fact in heroFacts" :key="fact">{{ fact }}</span>
          </div>
        </div>

        <div class="media-hero__body">
          <p v-if="item.description" class="media-summary__desc">
            {{ item.description }}
          </p>

          <ul v-if="freshPills.length" class="media-summary__fresh" aria-label="تازه‌ها">
            <li v-for="pill in freshPills" :key="pill">
              <CinematicIcon name="refresh" class="size-3.5" />
              {{ pill }}
            </li>
          </ul>

          <MediaActions
            :play-label="playLabel"
            :can-watch="canWatchOnline"
            :latest-label="latestRequest ? 'تماشای آخرین قسمت' : ''"
            :has-trailer="hasTrailer"
            :has-downloads="Boolean(downloadLinks.length)"
            :liked="liked"
            :content-id="item.id"
            :slug="item.slug"
            :content-type="item.type"
            @play="openPlayOptions"
            @latest="playLatest"
            @trailer="requestPlay('trailer')"
            @like="toggleLiked"
            @share="shareTitle"
            @downloads="openDownloadOptions"
            @party="startWatchParty"
            @collection="openCollectionModal"
          />
        </div>

        <MediaHeroRatings :item="item" class="media-hero__rates" />
      </div>
    </MediaHero>

    <MediaDetailTabs
      :tabs="detailTabs"
      :active-id="activeSection"
      @select="activateSection"
    />

    <div class="media-body">
      <div class="media-body__grid">
        <div class="min-w-0 space-y-10">
          <section id="story" class="media-section media-panel" aria-labelledby="story-title">
            <p class="media-panel__eyebrow">خلاصه داستان</p>
            <h2 id="story-title" class="media-panel__title">درباره {{ item.title }}</h2>
            <p v-if="item.description" class="media-panel__text">{{ item.description }}</p>
            <p v-else class="media-panel__text" style="color: var(--text-muted)">
              هنوز خلاصه‌ای برای این عنوان ثبت نشده است.
            </p>
          </section>

          <MediaDownloadSummary :item="item" @download="openDownloadOptions" />

          <ContentWarnings :warnings="item.content_warnings" />

          <MediaInfoGrid :item="item" />

          <MediaCastCarousel
            :cast="item.cast"
            :crew="item.crew"
            :director-fallback="hasDirector ? item.director : ''"
            @select="(kind, name) => trackPersonClick(kind, name, item)"
          />

          <MediaCommentsPanel
            :content-type="item.type"
            :object-id="item.id"
            :slug="item.slug"
            :title="item.title"
            :reviews="reviews"
            :my-rating="myRating"
            @refreshed="loadReviews"
          />

          <section
            v-if="authStore.isAuthenticated"
            id="why-recommended"
            class="media-section media-panel"
            style="background: linear-gradient(135deg, rgb(var(--media-accent-rgb) / 10%), var(--surface-1));"
          >
            <div class="flex items-start gap-4">
              <span
                class="grid size-12 shrink-0 place-items-center rounded-2xl ring-1"
                style="background: rgb(var(--media-accent-rgb) / 14%); color: var(--media-accent); box-shadow: inset 0 0 0 1px rgb(var(--media-accent-rgb) / 20%);"
              >
                <CinematicIcon name="ai" class="size-7" />
              </span>
              <div>
                <p class="media-panel__eyebrow">چرا این عنوان؟</p>
                <h2 class="media-panel__title">
                  {{ item.recommendation_reason || 'چون با سلیقه تو جور است' }}
                </h2>
                <NuxtLink
                  to="/profile#personalization"
                  class="mt-3 inline-flex min-h-10 items-center text-xs font-black"
                  style="color: var(--media-accent)"
                >
                  پیشنهادهای من
                </NuxtLink>
              </div>
            </div>
          </section>
        </div>

        <aside class="media-aside">
          <RatingWidget
            id="rate"
            :object-id="item.id"
            :slug="item.slug"
            :content-type="item.type"
          />

          <div class="media-panel">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-sm font-black text-[color:var(--text-primary)]">در یک نگاه</h2>
              <span class="inline-flex items-center gap-1 text-[11px] font-black text-[color:var(--accent-success)]">
                <span class="h-1.5 w-1.5 rounded-full bg-[color:var(--accent-success)]" />
                منتشر شده
              </span>
            </div>
            <dl class="mt-3 divide-y divide-[color:var(--border-color)] text-sm">
              <div class="flex items-start justify-between gap-4 py-3 first:pt-0">
                <dt class="text-[color:var(--text-muted)]">نوع محتوا</dt>
                <dd class="font-bold text-[color:var(--text-secondary)]">{{ item.type === 'movie' ? 'فیلم' : 'سریال' }}</dd>
              </div>
              <div
                v-if="item.imdb_rank"
                class="flex items-start justify-between gap-4 py-3"
              >
                <dt class="text-[color:var(--text-muted)]">IMDb Top 250</dt>
                <dd>
                  <NuxtLink
                    :to="item.type === 'movie' ? '/movies?sort=imdb_top' : '/series?sort=imdb_top'"
                    class="inline-flex items-center gap-1.5 rounded-lg bg-[#f5c518] px-2 py-1 text-xs font-black text-night-950 transition hover:brightness-105"
                    dir="ltr"
                  >
                    #{{ item.imdb_rank }}
                    <span class="opacity-70">/ 250</span>
                  </NuxtLink>
                </dd>
              </div>
              <div v-if="item.director" class="flex items-start justify-between gap-4 py-3">
                <dt class="text-[color:var(--text-muted)]">کارگردان</dt>
                <dd class="max-w-40 text-start">
                  <button
                    type="button"
                    class="font-bold text-[color:var(--text-secondary)] transition hover:text-[color:var(--media-accent)]"
                    @click="trackPersonClick('director', item.director, item)"
                  >
                    {{ item.director }}
                  </button>
                </dd>
              </div>
              <div v-if="item.age_rating" class="flex items-start justify-between gap-4 py-3">
                <dt class="text-[color:var(--text-muted)]">رده سنی</dt>
                <dd><AgeRatingBadge :rating="item.age_rating" /></dd>
              </div>
              <div class="flex items-start justify-between gap-4 py-3">
                <dt class="text-[color:var(--text-muted)]">نسخه پخش</dt>
                <dd class="text-start">
                  <DubSubtitleBadge
                    :is-dubbed="item.is_dubbed"
                    :has-subtitle="item.has_subtitle"
                    compact
                  />
                  <span
                    v-if="!item.is_dubbed && !item.has_subtitle"
                    class="text-xs font-bold text-[color:var(--text-secondary)]"
                  >زبان اصلی</span>
                </dd>
              </div>
              <div v-if="item.type === 'series'" class="flex items-start justify-between gap-4 py-3">
                <dt class="text-[color:var(--text-muted)]">قسمت‌ها</dt>
                <dd class="font-bold text-[color:var(--text-secondary)]">{{ episodeCount || 'به‌زودی' }}</dd>
              </div>
            </dl>
          </div>

          <div v-if="canWatchOnline" class="media-aside__cta hidden lg:block">
            <CinematicIcon name="resume" class="size-8" />
            <h2>آماده تماشا هستی؟</h2>
            <p>پخش از همان جایی که رها کردی ادامه پیدا می‌کند.</p>
            <button type="button" @click="openPlayOptions">
              <CinematicIcon name="play" class="size-4" filled />
              {{ playLabel }}
            </button>
          </div>
        </aside>
      </div>

      <div class="mt-10 space-y-8">
        <LazyMovieRow
          v-if="sameGenreTitles.length"
          :hydrate-on-visible="{ rootMargin: '320px 0px' }"
          :title="`بیشتر از ژانر ${primaryGenre?.title}`"
          eyebrow="در همان حال‌وهوا"
          :items="sameGenreTitles"
          :href="`/${item.type === 'movie' ? 'movies' : 'series'}/genre/${primaryGenre?.slug}`"
        />
        <LazyMovieRow
          v-if="related.length"
          id="similar"
          :hydrate-on-visible="{ rootMargin: '320px 0px' }"
          title="آثار مشابه"
          eyebrow="انتخاب‌های نزدیک به این عنوان"
          :items="related"
        />
        <CollectionInCollections
          :content-type="item.type"
          :object-id="item.id"
          :title="item.title"
        />
      </div>
      <div class="h-10" />
    </div>
  </article>

  <MediaAccessModal
    :open="Boolean(accessModal)"
    :mode="accessModal || 'play'"
    :links="downloadLinks"
    :title="item.title"
    :slug="item.slug"
    :accent-style="styleVars"
    @close="accessModal = null"
    @play="playSelectedVersion"
    @download="quality => trackDownload(item, quality)"
  />
  <ConfirmAdultContentModal :open="modalOpen" :title="item.title" @close="modalOpen = false" @confirm="confirmPlay" />
  <CollectionAddModal
    :open="collectionOpen"
    :content-type="item.type"
    :object-id="item.id"
    :title="item.title"
    @close="collectionOpen = false"
  />
</template>
