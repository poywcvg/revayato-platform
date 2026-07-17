<script setup lang="ts">
import type { ContentType, PlaybackQuality, WatchRoom } from '~/types'

definePageMeta({ layout: 'player' })

const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const slug = computed(() => String(route.params.slug))
const { catalog, loadItemFromApi } = useCatalog()
const authStore = useAuthStore()
const { api } = useApi()
const notifications = useNotifications()
const initialItem = catalog.value.find(candidate => candidate.slug === slug.value)
const requestedType = route.query.type === 'movie' || route.query.type === 'series'
  ? route.query.type as ContentType
  : initialItem?.type

if (config.public.catalogSource === 'api') {
  if (requestedType) await loadItemFromApi(slug.value, requestedType)
  else if (!await loadItemFromApi(slug.value, 'movie')) await loadItemFromApi(slug.value, 'series')
}

const item = computed(() => catalog.value.find(candidate => candidate.slug === slug.value) ?? null)
const { trackTrailerPlay, trackWatchProgress } = useAnalyticsEvent()

if (!item.value) throw createError({ statusCode: 404, statusMessage: 'محتوا پیدا نشد' })

const mode = computed(() => route.query.mode === 'trailer' ? 'trailer' : 'full')
const restricted = computed(() => item.value?.age_rating === '18+')
const confirmed = ref(!restricted.value || route.query.confirmed === '1')
const modalOpen = ref(restricted.value && !confirmed.value)
const detailPath = computed(() => `/${item.value?.type === 'movie' ? 'movies' : 'series'}/${item.value?.slug}`)
const related = useRelatedMovies(item, 6)
const orderedEpisodes = computed(() => [...(item.value?.episodes || [])].sort((a, b) => (a.season_number || 1) - (b.season_number || 1) || a.episode_number - b.episode_number))
const requestedEpisodeId = computed(() => Number(route.query.episode) || 0)
const currentEpisode = computed(() => orderedEpisodes.value.find(episode => episode.id === requestedEpisodeId.value) || orderedEpisodes.value.find(episode => (episode.progress_percent || 0) > 0 && !episode.is_watched) || orderedEpisodes.value.find(episode => !episode.is_watched) || orderedEpisodes.value[0])
const nextEpisode = computed(() => {
  const currentIndex = orderedEpisodes.value.findIndex(episode => episode.id === currentEpisode.value?.id)
  return currentIndex >= 0 ? orderedEpisodes.value[currentIndex + 1] : undefined
})
const playerSource = computed(() => {
  if (mode.value === 'trailer') return item.value?.trailer_url || ''
  return currentEpisode.value?.hls_url
    || item.value?.playback?.signed_playback_url
    || item.value?.playback?.hls_url
    || item.value?.hls_url
    || ''
})
const resumeProgress = computed(() => {
  if (mode.value === 'trailer') return 0
  return Math.min(95, Math.max(0, currentEpisode.value?.progress_percent ?? item.value?.progress_percent ?? 0))
})
const playbackLabel = computed(() => currentEpisode.value
  ? `فصل ${currentEpisode.value.season_number || 1} · قسمت ${currentEpisode.value.episode_number}`
  : item.value?.title || '')
const selectedQuality = ref<PlaybackQuality>('auto')
const liveProgress = ref(resumeProgress.value)
const playerNotice = ref('')
const creatingParty = ref(false)
let noticeTimer: number | undefined

watch([resumeProgress, () => currentEpisode.value?.id, mode], () => {
  liveProgress.value = resumeProgress.value
})

function confirmPlayback() {
  confirmed.value = true
  modalOpen.value = false
  void router.replace({ query: { ...route.query, confirmed: '1' } })
}

function leavePlayer() {
  modalOpen.value = false
  void navigateTo(detailPath.value)
}

function handlePlaybackStart(progress: number) {
  if (!item.value) return
  liveProgress.value = progress
  if (mode.value === 'trailer') trackTrailerPlay(item.value)
  else trackWatchProgress(item.value, progress, 'start')
}

function handlePlaybackPause(progress: number) {
  liveProgress.value = progress
  if (item.value && mode.value === 'full') trackWatchProgress(item.value, progress, 'pause')
}

function handlePlaybackProgress(progress: number) {
  liveProgress.value = progress
  if (item.value && mode.value === 'full') trackWatchProgress(item.value, progress, 'progress')
}

function handlePlaybackComplete(progress: number) {
  liveProgress.value = progress
  if (item.value && mode.value === 'full') trackWatchProgress(item.value, progress, 'complete')
}

function showPlayerNotice(message: string) {
  playerNotice.value = message
  if (noticeTimer) window.clearTimeout(noticeTimer)
  noticeTimer = window.setTimeout(() => { playerNotice.value = '' }, 2400)
}

function selectQuality(quality: PlaybackQuality) {
  selectedQuality.value = quality
  showPlayerNotice(quality === 'auto' ? 'کیفیت خودکار فعال شد' : `کیفیت ${quality} انتخاب شد`)
}

function playNextEpisode() {
  if (!nextEpisode.value) return showPlayerNotice('قسمت بعدی در دسترس نیست')
  void router.replace({ query: { ...route.query, type: 'series', episode: nextEpisode.value.id } })
  showPlayerNotice(`در حال آماده‌سازی: ${nextEpisode.value.title}`)
}

async function createWatchParty() {
  if (!authStore.isAuthenticated) {
    await navigateTo({ path: '/auth/login', query: { redirect: route.fullPath } })
    return
  }
  if (!item.value || creatingParty.value) return
  const contentType = currentEpisode.value ? 'episode' : item.value.type === 'movie' ? 'movie' : null
  const contentId = currentEpisode.value?.id || item.value.id
  if (!contentType) {
    showPlayerNotice('برای ساخت اتاق، ابتدا یک قسمت را انتخاب کنید')
    return
  }
  creatingParty.value = true
  try {
    const room = await api<WatchRoom>('/watch-party/rooms/', {
      method: 'POST',
      body: { content_type: contentType, content_id: contentId },
    })
    await navigateTo(`/watch-party/${room.invite_code}`)
  } catch (cause) {
    const failure = getAppError(cause, 'ساخت اتاق تماشای گروهی ممکن نشد.')
    showPlayerNotice(failure.message)
    notifications.error(failure.title, failure.message)
  } finally {
    creatingParty.value = false
  }
}

onBeforeUnmount(() => {
  if (noticeTimer) window.clearTimeout(noticeTimer)
})

useSeoMeta({
  title: () => item.value ? `${mode.value === 'trailer' ? 'تریلر' : 'تماشای'} ${item.value.title}` : 'پخش',
  description: () => item.value?.description || '',
})
</script>

<template>
  <div v-if="item" class="cinema-page min-h-dvh text-ink">
    <div class="page-shell py-3 sm:py-7 lg:py-9">
      <header class="mb-5 flex items-center justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3">
          <NuxtLink :to="detailPath" class="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-white/5 px-3 text-slate-300 ring-1 ring-white/10 transition hover:bg-white/10 hover:text-white" aria-label="بازگشت به جزئیات"><CinematicIcon name="arrow-right" class="size-5" /><span class="hidden text-xs font-black sm:inline">بازگشت به جزئیات</span></NuxtLink>
          <div class="min-w-0"><p class="text-xs font-bold text-primary-400">{{ mode === 'trailer' ? 'پخش تریلر' : item.type === 'series' && currentEpisode ? `فصل ${currentEpisode.season_number || 1} · قسمت ${currentEpisode.episode_number}` : 'در حال تماشا' }}</p><h1 class="truncate text-lg font-black sm:text-2xl">{{ item.title }}<span v-if="mode === 'full' && currentEpisode" class="font-medium text-slate-400"> · {{ currentEpisode.title }}</span></h1></div>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <button v-if="mode === 'full'" type="button" :disabled="creatingParty" class="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-primary-500 px-3 text-xs font-black text-night-950 transition hover:bg-primary-400 active:bg-primary-600 disabled:bg-disabled" @click="createWatchParty"><CinematicIcon name="users" class="size-4" /><span class="hidden md:inline">تماشای گروهی</span><span v-if="creatingParty" class="size-3 animate-spin rounded-full border border-night-950/30 border-t-night-950" /></button>
          <div class="hidden items-center gap-2 sm:flex"><AgeRatingBadge :rating="item.age_rating" /></div>
        </div>
      </header>

      <section v-if="confirmed" aria-label="پخش‌کننده ویدیو">
        <div class="relative"><VideoPlayer :src="playerSource" :poster="currentEpisode?.thumbnail_url || item.playback?.poster_url || item.backdrop_url" :title="currentEpisode ? `${item.title} - ${currentEpisode.title}` : item.title" :start-at-percent="resumeProgress" :quality="selectedQuality" :subtitle-tracks="item.playback?.subtitle_tracks || []" @play="handlePlaybackStart" @pause="handlePlaybackPause" @progress="handlePlaybackProgress" @position="liveProgress = $event" @complete="handlePlaybackComplete" /><Transition enter-active-class="transition duration-150" enter-from-class="translate-y-1 opacity-0" leave-active-class="transition duration-100" leave-to-class="translate-y-1 opacity-0"><div v-if="playerNotice" class="absolute bottom-3 left-1/2 z-20 max-w-[calc(100%-1.5rem)] -translate-x-1/2 truncate rounded-xl bg-black/90 px-3 py-2 text-xs font-bold text-white ring-1 ring-white/15 sm:bottom-5 sm:px-4 sm:py-2.5">{{ playerNotice }}</div></Transition></div>
        <PlayerOptionsBar v-if="mode === 'full'" :audio-languages="item.audio_languages" :subtitle-languages="item.subtitle_languages" :has-next-episode="Boolean(nextEpisode)" @audio-change="showPlayerNotice(`صدای ${$event} انتخاب شد`)" @subtitle-change="showPlayerNotice($event === 'خاموش' ? 'زیرنویس خاموش شد' : `زیرنویس ${$event} انتخاب شد`)" @quality-change="selectQuality" @skip-intro="showPlayerNotice('تیتراژ در نسخه نمایشی رد شد')" @next-episode="playNextEpisode" />
        <PlaybackStatus v-if="mode === 'full'" :percent="liveProgress" :duration-minutes="currentEpisode?.duration_minutes || item.duration_minutes" :label="playbackLabel" />
        <div class="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div class="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10 sm:p-5"><div class="flex flex-wrap items-start justify-between gap-4"><div class="min-w-0"><h2 class="text-base font-black sm:text-lg">{{ mode === 'trailer' ? `تریلر ${item.title}` : currentEpisode ? `${item.title} · ${currentEpisode.title}` : item.title }}</h2><p class="mt-1 text-xs leading-6 text-slate-400 sm:text-sm">{{ item.year }} · {{ currentEpisode?.duration_minutes || item.duration_minutes }} دقیقه · {{ item.genres.map(genre => genre.title).join('، ') }}</p></div><WatchlistButton :id="item.id" :slug="item.slug" :content-type="item.type" dark compact-on-mobile /></div><p class="mt-4 max-w-3xl text-sm leading-7 text-slate-300">{{ currentEpisode?.description || item.description }}</p></div>
          <ContentWarnings :warnings="item.content_warnings" compact dark />
        </div>
        <div class="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5 text-xs text-muted"><p>کیفیت پخش با سرعت اینترنت شما هماهنگ می‌شود.</p><p class="inline-flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-success" />پخش تطبیقی فعال</p></div>
        <LazyMovieRow v-if="related.length" :hydrate-on-visible="{ rootMargin: '320px 0px' }" title="بعدش چی ببینم؟" eyebrow="پیشنهادهای بعد از این عنوان" :items="related" :href="item.type === 'movie' ? '/movies' : '/series'" dark />
      </section>

      <section v-else class="relative grid min-h-[360px] place-items-center overflow-hidden rounded-2xl bg-slate-950 ring-1 ring-white/10 sm:aspect-video sm:min-h-0">
        <NuxtImg :src="item.backdrop_url" alt="" class="absolute inset-0 h-full w-full object-cover opacity-15" />
        <div class="relative max-w-md p-6 text-center"><span class="mx-auto grid size-14 place-items-center rounded-2xl bg-error/15 text-error ring-1 ring-error/25"><CinematicIcon name="lock" class="size-7" /></span><h2 class="mt-4 text-xl font-black">پخش تا زمان تأیید متوقف است</h2><p class="mt-2 text-sm leading-7 text-secondary">این عنوان برای رده سنی بزرگسال است و پیش از بارگذاری و پخش به تأیید نیاز دارد.</p><button type="button" class="mt-5 rounded-xl bg-primary-500 px-5 py-3 text-sm font-black text-night-950 hover:bg-primary-400" @click="modalOpen = true">بررسی و ادامه</button></div>
      </section>
    </div>
    <ConfirmAdultContentModal :open="modalOpen" :title="item.title" @confirm="confirmPlayback" @close="leavePlayer" />
  </div>
</template>
