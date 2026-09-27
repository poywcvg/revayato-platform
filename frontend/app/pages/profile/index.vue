<script setup lang="ts">
import type { CinematicIconName } from '~/types'

definePageMeta({ middleware: 'auth' })

const { catalog } = useCatalog()
const { watchlist, likes } = useLibrary()
const { continueWatching } = useWatchProgress()
const { stats: watchTimeStats } = useWatchTime()
const { myCollections, loaded: collectionsLoaded, refreshMine } = useCollections()
const authStore = useAuthStore()
const notifications = useNotifications()
const route = useRoute()

/* ---------- identity ---------- */

const displayName = computed(() => authStore.user?.username || 'کاربر روایتو')
const avatarInitial = computed(() => displayName.value.trim().charAt(0).toUpperCase() || 'ر')
const profileBio = computed(() => authStore.user?.profile.bio?.trim() || '')
const isVerified = computed(() => Boolean(authStore.user?.is_verified || authStore.user?.profile.is_email_verified))
const publicProfilePath = computed(() => (authStore.user?.username ? `/u/${authStore.user.username}` : '/profile'))
const memberSince = computed(() => {
  const value = authStore.user?.profile.created_at
  if (!value) return 'همین تازگی'
  try {
    return new Intl.DateTimeFormat('fa-IR', { year: 'numeric', month: 'long' }).format(new Date(value))
  } catch {
    return 'همین تازگی'
  }
})

const watchTimeLabel = computed(() => {
  const { hours, minutes } = watchTimeStats.value
  if (hours <= 0 && minutes <= 0) return '۰ دقیقه'
  if (hours <= 0) return `${minutes.toLocaleString('fa-IR')} دقیقه`
  if (minutes <= 0) return `${hours.toLocaleString('fa-IR')} ساعت`
  return `${hours.toLocaleString('fa-IR')}س ${minutes.toLocaleString('fa-IR')}د`
})

/* ---------- tabs ----------
 * One navigation replaces the three the page used to carry (a mobile anchor
 * rail, a proximity sidebar and a quick-links panel). Panels mount on first
 * visit and stay mounted, so switching back never re-runs their fetches.
 */

type TabId = 'overview' | 'activity' | 'settings'

const TABS = [
  { id: 'overview', label: 'نمای کلی', icon: 'grid' },
  { id: 'activity', label: 'فعالیت', icon: 'clock' },
  { id: 'settings', label: 'تنظیمات', icon: 'sliders' },
] as const satisfies ReadonlyArray<{ id: TabId; label: string; icon: CinematicIconName }>

// Links elsewhere in the app still point at the old section anchors
// (/profile#continue, /profile#personalization) — they must keep landing
// somewhere sensible now that the sections live behind tabs.
const HASH_TO_TAB: Record<string, TabId> = {
  overview: 'overview',
  continue: 'overview',
  collections: 'overview',
  watchlist: 'overview',
  activity: 'activity',
  'watch-time': 'activity',
  'behavior-insight': 'activity',
  settings: 'settings',
  personalization: 'settings',
  account: 'settings',
}

const activeTab = ref<TabId>('overview')
const mountedTabs = reactive<Record<TabId, boolean>>({ overview: false, activity: false, settings: false })
const tabsBar = useTemplateRef<HTMLElement>('tabsBar')
const tabButtons = ref<HTMLButtonElement[]>([])

watch(activeTab, (id) => { mountedTabs[id] = true }, { immediate: true })

function tabFromHash(hash: string): TabId | null {
  return HASH_TO_TAB[hash.replace(/^#/, '')] ?? null
}

// The hash never reaches the server, so it is resolved after mount to keep
// server and client markup identical.
onMounted(() => {
  const fromHash = tabFromHash(route.hash)
  if (fromHash) activeTab.value = fromHash
  void refreshMine()
})

watch(() => route.hash, (hash) => {
  const target = tabFromHash(hash)
  if (target) activeTab.value = target
})

// `reveal` is for switches triggered from outside the tab bar (the stat
// strip): the panel changes below the fold, so bring the tabs into view to
// show what happened.
function selectTab(id: TabId, reveal = false) {
  if (activeTab.value === id) {
    if (reveal) revealTabs()
    return
  }
  activeTab.value = id
  if (!import.meta.client) return
  // replaceState instead of the router: the tab is already switched, and a
  // router hash change would trigger the scroll-to-anchor behaviour.
  history.replaceState(history.state, '', `${route.path}#${id}`)
  nextTick(() => {
    if (reveal || (tabsBar.value?.getBoundingClientRect().top ?? 0) < 0) revealTabs()
  })
}

function revealTabs() {
  tabsBar.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onTabKeydown(event: KeyboardEvent, index: number) {
  const last = TABS.length - 1
  let next = -1
  // RTL: ArrowLeft advances, ArrowRight goes back.
  if (event.key === 'ArrowLeft') next = index === last ? 0 : index + 1
  else if (event.key === 'ArrowRight') next = index === 0 ? last : index - 1
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = last
  if (next < 0) return
  event.preventDefault()
  const target = TABS[next]
  if (!target) return
  selectTab(target.id)
  nextTick(() => tabButtons.value[next]?.focus())
}

/* ---------- content ---------- */

const stats = computed<Array<{ key: string; label: string; value: string; to?: string; tab?: TabId }>>(() => [
  { key: 'time', label: 'زمان تماشا', value: watchTimeLabel.value, tab: 'activity' },
  { key: 'watchlist', label: 'لیست من', value: watchlist.value.length.toLocaleString('fa-IR'), to: '/watchlist' },
  { key: 'likes', label: 'پسندیده‌ها', value: likes.value.length.toLocaleString('fa-IR'), to: '/profile/favorites' },
  { key: 'done', label: 'کامل دیده‌شده', value: watchTimeStats.value.titles_completed.toLocaleString('fa-IR'), tab: 'activity' },
])

const continueItems = computed(() => continueWatching.value.slice(0, 6))
const topCollections = computed(() => myCollections.value.slice(0, 3))
const watchlistItems = computed(() => catalog.value.filter(item =>
  watchlist.value.some(entry => entry.content_type === item.type && entry.object_id === item.id),
).slice(0, 10))

const accountLinks = computed<Array<{ label: string; hint: string; icon: CinematicIconName; to: string }>>(() => [
  { label: 'نمای عمومی پروفایل', hint: 'همان چیزی که دیگران می‌بینند', icon: 'user', to: publicProfilePath.value },
  { label: 'کالکشن‌های من', hint: 'فهرست‌های شخصی و اشتراکی', icon: 'layers', to: '/collections/my' },
  { label: 'درخواست‌های من', hint: 'گفت‌وگو و پاسخ پشتیبانی', icon: 'comments', to: '/requests' },
])

/* ---------- actions ---------- */

const editOpen = ref(false)

async function logout() {
  await authStore.logout()
  notifications.info('از حساب خارج شدی', 'نشست این دستگاه با امنیت بسته شد.')
  await navigateTo('/')
}

const visibilityHydration = { rootMargin: '320px 0px' }
useSeoMeta({ title: 'پروفایل من', description: 'مدیریت پروفایل، ادامه تماشا، ساعت تماشا و فهرست شخصی.' })
</script>

<template>
  <div class="cinema-page pb-14 sm:pb-20">
    <section class="page-section pb-3 pt-3 sm:pt-6">
      <header class="pf-card pf-identity">
        <button type="button" class="pf-avatar" aria-label="ویرایش تصویر پروفایل" @click="editOpen = true">
          <img v-if="authStore.user?.profile.avatar" :src="authStore.user.profile.avatar" alt="" class="size-full object-cover">
          <span v-else>{{ avatarInitial }}</span>
          <span class="pf-avatar__edit" aria-hidden="true"><CinematicIcon name="edit" class="size-3.5" /></span>
        </button>

        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h1 class="pf-name font-latin" dir="ltr">{{ displayName }}</h1>
            <span v-if="isVerified" class="pf-verified"><CinematicIcon name="shield-check" class="size-3.5" />تأییدشده</span>
          </div>

          <p v-if="profileBio" class="pf-bio">{{ profileBio }}</p>
          <button v-else type="button" class="pf-bio pf-bio--empty" @click="editOpen = true">
            معرفی کوتاهی درباره خودت بنویس…
          </button>

          <p class="pf-meta">عضو روایتو از {{ memberSince }}</p>
        </div>

        <div class="pf-identity__actions">
          <button type="button" class="ui-secondary-button pf-edit" aria-label="ویرایش پروفایل" @click="editOpen = true">
            <CinematicIcon name="edit" class="size-4" />
            <span class="pf-edit__label">ویرایش پروفایل</span>
          </button>
        </div>
      </header>

      <div class="pf-stats" aria-label="خلاصه فعالیت حساب">
        <template v-for="stat in stats" :key="stat.key">
          <NuxtLink v-if="stat.to" :to="stat.to" class="pf-stat">
            <strong>{{ stat.value }}</strong>
            <span>{{ stat.label }}</span>
          </NuxtLink>
          <button v-else type="button" class="pf-stat" @click="stat.tab && selectTab(stat.tab, true)">
            <strong>{{ stat.value }}</strong>
            <span>{{ stat.label }}</span>
          </button>
        </template>
      </div>
    </section>

    <div ref="tabsBar" class="pf-tabs">
      <div class="pf-tabs__inner" role="tablist" aria-label="بخش‌های پروفایل">
        <button
          v-for="(tab, index) in TABS"
          :id="`pf-tab-${tab.id}`"
          :key="tab.id"
          :ref="(el) => { if (el) tabButtons[index] = el as HTMLButtonElement }"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.id"
          :aria-controls="`pf-panel-${tab.id}`"
          :tabindex="activeTab === tab.id ? 0 : -1"
          class="pf-tab"
          :class="activeTab === tab.id && 'is-active'"
          @click="selectTab(tab.id)"
          @keydown="onTabKeydown($event, index)"
        >
          <CinematicIcon :name="tab.icon" class="size-4" />
          {{ tab.label }}
        </button>
      </div>
    </div>

    <div
      v-if="mountedTabs.overview"
      v-show="activeTab === 'overview'"
      id="pf-panel-overview"
      role="tabpanel"
      aria-labelledby="pf-tab-overview"
      tabindex="0"
      class="pf-panel"
    >
      <section class="content-section">
        <SectionHeader
          title="ادامه تماشا"
          href="/movies"
          link-label="پیدا کردن عنوان"
          icon="resume"
        />
        <div v-if="continueItems.length" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <ContinueWatchingCard v-for="item in continueItems" :key="`${item.type}-${item.id}`" :item="item" />
        </div>
        <EmptyState
          v-else
          title="هنوز چیزی در حال تماشا نیست"
          description="پخش یک فیلم یا سریال را شروع کن؛ ادامه‌اش از همین‌جا در دسترس می‌ماند."
          icon="resume"
          action-label="مرور فیلم‌ها"
          action-href="/movies"
        />
      </section>

      <LazyMovieRow
        v-if="watchlistItems.length"
        :hydrate-on-visible="visibilityHydration"
        title="لیست من"
        :items="watchlistItems"
        href="/watchlist"
        icon="bookmark"
      />

      <section class="content-section">
        <SectionHeader
          title="کالکشن‌های من"
          href="/collections/my"
          link-label="همه کالکشن‌ها"
          icon="layers"
        >
          <template #actions>
            <NuxtLink to="/collections/my" class="ui-secondary-button min-h-11 px-3 text-xs">
              <CinematicIcon name="plus" class="size-4" />کالکشن جدید
            </NuxtLink>
          </template>
        </SectionHeader>

        <div v-if="!collectionsLoaded" class="grid place-items-center py-12">
          <LoadingSpinnerA size="small" />
        </div>
        <div v-else-if="topCollections.length" class="pf-collections">
          <CollectionSummaryCard
            v-for="collection in topCollections"
            :key="collection.id"
            :collection="collection"
            :to="`/collections/my/${collection.slug}`"
          />
        </div>
        <EmptyState
          v-else
          title="هنوز کالکشنی نساخته‌ای"
          description="اولین فهرستت را بساز؛ مثلاً «شاهکارهای سینما» یا «برای یک شب بارانی»."
          icon="layers"
          action-label="ساخت اولین کالکشن"
          action-href="/collections/my"
        />
      </section>
    </div>

    <div
      v-if="mountedTabs.activity"
      v-show="activeTab === 'activity'"
      id="pf-panel-activity"
      role="tabpanel"
      aria-labelledby="pf-tab-activity"
      tabindex="0"
      class="pf-panel"
    >
      <WatchTimeStory />
      <LazyBehaviorInsight :hydrate-on-visible="visibilityHydration" />
    </div>

    <div
      v-if="mountedTabs.settings"
      v-show="activeTab === 'settings'"
      id="pf-panel-settings"
      role="tabpanel"
      aria-labelledby="pf-tab-settings"
      tabindex="0"
      class="pf-panel"
    >
      <LazyPersonalizationSettings :hydrate-on-visible="visibilityHydration" />

      <section class="content-section" aria-label="حساب کاربری">
        <SectionHeader title="حساب کاربری" icon="user" />

        <div class="pf-card pf-account">
          <div class="pf-row pf-row--static">
            <span class="pf-row__icon"><CinematicIcon :name="isVerified ? 'shield-check' : 'shield-alert'" class="size-4.5" /></span>
            <span class="min-w-0 flex-1">
              <strong>ایمیل حساب</strong>
              <small class="font-latin" dir="ltr">{{ authStore.user?.email }}</small>
            </span>
            <span class="pf-badge" :class="isVerified ? 'pf-badge--ok' : 'pf-badge--warn'">
              {{ isVerified ? 'تأییدشده' : 'تأیید نشده' }}
            </span>
          </div>

          <NuxtLink v-for="link in accountLinks" :key="link.to" :to="link.to" class="pf-row">
            <span class="pf-row__icon"><CinematicIcon :name="link.icon" class="size-4.5" /></span>
            <span class="min-w-0 flex-1">
              <strong>{{ link.label }}</strong>
              <small>{{ link.hint }}</small>
            </span>
            <CinematicIcon name="arrow-left" class="size-4 shrink-0 text-disabled" />
          </NuxtLink>

          <button type="button" class="pf-row pf-row--danger" @click="logout">
            <span class="pf-row__icon"><CinematicIcon name="logout" class="size-4.5" /></span>
            <span class="min-w-0 flex-1">
              <strong>خروج از حساب</strong>
              <small>نشست این دستگاه بسته می‌شود</small>
            </span>
          </button>
        </div>
      </section>
    </div>

    <ProfileEditorModal :open="editOpen" @close="editOpen = false" />
  </div>
</template>

<style scoped>
/* One card shape for the whole page — no gradients, no glow layers. */
.pf-card {
  border: 1px solid color-mix(in srgb, var(--theme-border) 80%, transparent);
  border-radius: 1.15rem;
  background: var(--theme-bg-surface);
}

/* ---- identity ---- */

.pf-identity {
  display: flex;
  align-items: flex-start;
  gap: .9rem;
  padding: 1rem;
}

.pf-avatar {
  position: relative;
  display: grid;
  width: 4rem;
  height: 4rem;
  flex: none;
  place-items: center;
  overflow: hidden;
  border-radius: 1.15rem;
  background: linear-gradient(145deg, var(--theme-accent-primary), var(--theme-primary-700));
  color: var(--theme-on-accent);
  font-family: var(--font-latin-ui);
  font-size: 1.4rem;
  font-weight: 800;
  cursor: pointer;
}

.pf-avatar:focus-visible { outline: 3px solid var(--theme-focus-ring); outline-offset: 3px; }

.pf-avatar__edit {
  position: absolute;
  inset: auto auto .15rem .15rem;
  display: grid;
  width: 1.4rem;
  height: 1.4rem;
  place-items: center;
  border-radius: .5rem;
  background: rgb(5 8 7 / 82%);
  color: white;
}

.pf-name {
  overflow-wrap: anywhere;
  color: var(--theme-text-primary);
  font-size: 1.3rem;
  font-weight: 800;
  line-height: 1.2;
}

.pf-verified {
  display: inline-flex;
  align-items: center;
  gap: .25rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-success) 12%, transparent);
  padding: .15rem .45rem;
  color: var(--theme-success);
  font-size: 0.75rem;
  font-weight: 800;
}

.pf-bio {
  display: -webkit-box;
  overflow: hidden;
  margin-top: .35rem;
  max-width: 44rem;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  color: var(--theme-text-secondary);
  font-size: .78rem;
  line-height: 1.75;
}

.pf-bio--empty {
  text-align: start;
  color: var(--theme-text-muted);
  text-decoration: underline;
  text-decoration-style: dotted;
  text-underline-offset: 3px;
  cursor: pointer;
}

.pf-bio--empty:hover { color: var(--theme-accent-primary); }

.pf-meta {
  margin-top: .35rem;
  color: var(--theme-text-muted);
  font-size: 0.75rem;
}

.pf-identity__actions { flex: none; }

.pf-edit {
  min-height: 2.75rem;
  gap: .4rem;
  padding: .5rem;
  aspect-ratio: 1;
  font-size: .75rem;
}

.pf-edit__label { display: none; }

/* ---- stats ---- */

.pf-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: .6rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 80%, transparent);
  border-radius: 1.15rem;
  background: var(--theme-bg-surface);
  overflow: hidden;
}

.pf-stat {
  display: flex;
  min-width: 0;
  min-height: 3.75rem;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: .15rem;
  padding: .6rem .35rem;
  text-align: center;
  transition: background-color 150ms ease;
}

.pf-stat + .pf-stat { border-inline-start: 1px solid color-mix(in srgb, var(--theme-border) 70%, transparent); }
.pf-stat:hover, .pf-stat:focus-visible { background: color-mix(in srgb, var(--theme-accent-primary) 7%, transparent); }
.pf-stat strong { overflow: hidden; max-width: 100%; text-overflow: ellipsis; white-space: nowrap; color: var(--theme-text-primary); font-size: .85rem; font-weight: 900; }
.pf-stat span { color: var(--theme-text-muted); font-size: 0.75rem; }

/* ---- tabs ---- */

.pf-tabs {
  position: sticky;
  top: var(--sticky-offset);
  z-index: 20;
  border-bottom: 1px solid color-mix(in srgb, var(--theme-border) 65%, transparent);
  background: color-mix(in srgb, var(--theme-bg-main) 90%, transparent);
  backdrop-filter: blur(14px);
}

.pf-tabs__inner {
  display: flex;
  gap: .25rem;
  inline-size: 100%;
  max-inline-size: var(--layout-max);
  margin-inline: auto;
  padding-inline: var(--layout-gutter);
}

.pf-tab {
  position: relative;
  display: inline-flex;
  min-height: 2.9rem;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: .4rem;
  padding: .5rem .5rem;
  color: var(--theme-text-muted);
  font-size: .78rem;
  font-weight: 800;
  transition: color 150ms ease;
}

.pf-tab::after {
  content: '';
  position: absolute;
  inset-inline: .5rem;
  bottom: -1px;
  height: 2px;
  border-radius: 999px;
  background: transparent;
  transition: background-color 180ms ease;
}

.pf-tab:hover { color: var(--theme-text-secondary); }
.pf-tab.is-active { color: var(--theme-text-primary); }
.pf-tab.is-active::after { background: var(--theme-accent-primary); }
.pf-tab:focus-visible { outline: 2px solid var(--theme-focus-ring); outline-offset: -3px; border-radius: .6rem; }

.pf-panel:focus-visible { outline: none; }

/* ---- collections ---- */

.pf-collections {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 15rem), 1fr));
  gap: 1rem;
}

/* ---- account rows ---- */

.pf-account { overflow: hidden; }

.pf-row {
  display: flex;
  width: 100%;
  min-height: 3.75rem;
  align-items: center;
  gap: .75rem;
  padding: .7rem .9rem;
  text-align: start;
  transition: background-color 150ms ease;
}

.pf-row + .pf-row { border-top: 1px solid color-mix(in srgb, var(--theme-border) 60%, transparent); }
.pf-row:not(.pf-row--static):hover,
.pf-row:not(.pf-row--static):focus-visible { background: var(--theme-bg-elevated); }
.pf-row strong { display: block; color: var(--theme-text-primary); font-size: .8rem; font-weight: 800; }
.pf-row small { display: block; overflow: hidden; margin-top: .15rem; text-overflow: ellipsis; white-space: nowrap; color: var(--theme-text-muted); font-size: 0.75rem; }

.pf-row__icon {
  display: grid;
  width: 2.25rem;
  height: 2.25rem;
  flex: none;
  place-items: center;
  border-radius: .75rem;
  background: color-mix(in srgb, var(--theme-accent-primary) 10%, transparent);
  color: var(--theme-accent-primary);
}

.pf-row--danger .pf-row__icon { background: rgb(239 68 68 / 12%); color: var(--theme-error); }
.pf-row--danger strong { color: var(--theme-error); }
.pf-row--danger:hover { background: rgb(239 68 68 / 8%); }

.pf-badge { flex: none; border-radius: 999px; padding: .2rem .5rem; font-size: 0.75rem; font-weight: 800; }
.pf-badge--ok { background: color-mix(in srgb, var(--theme-success) 12%, transparent); color: var(--theme-success); }
.pf-badge--warn { background: rgb(234 179 8 / 14%); color: rgb(250 204 21); }

@media (min-width: 640px) {
  .pf-card { border-radius: 1.35rem; }
  .pf-identity { padding: 1.25rem 1.35rem; }
  .pf-avatar { width: 4.75rem; height: 4.75rem; font-size: 1.6rem; }
  .pf-name { font-size: 1.6rem; }
  .pf-edit { aspect-ratio: auto; padding: .5rem .9rem; }
  .pf-edit__label { display: inline; }
  .pf-stats { border-radius: 1.35rem; }
  .pf-stat strong { font-size: .95rem; }
  .pf-stat span { font-size: 0.75rem; }
  .pf-tab { flex: none; padding-inline: 1rem; font-size: .82rem; }
}

@media (max-width: 359px) {
  .pf-identity { padding: .8rem; gap: .65rem; }
  .pf-avatar { width: 3.4rem; height: 3.4rem; font-size: 1.15rem; }
  .pf-name { font-size: 1.1rem; }
  .pf-bio { -webkit-line-clamp: 1; }
  .pf-tab { gap: .25rem; font-size: 0.75rem; }
}

@media (prefers-reduced-motion: reduce) {
  .pf-stat, .pf-tab, .pf-tab::after, .pf-row { transition: none; }
}
</style>
