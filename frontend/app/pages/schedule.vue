<script setup lang="ts">
interface ScheduleEntry {
  type: 'episode' | 'movie'
  air_date: string
  released: boolean
  series_slug: string
  series_title: string
  series_original_title: string
  poster_url: string | null
  season_number: number | null
  episode_number: number | null
  episode_title: string | null
  imdb_rating: string | null
  content_format: string
  is_dubbed: boolean
  has_subtitle: boolean
}

interface ScheduleDay {
  date: string
  weekday: number
  weekday_label: string
  is_today: boolean
  count: number
  entries: ScheduleEntry[]
}

interface ScheduleResponse {
  start: string
  end: string
  today: string
  days: ScheduleDay[]
  total: number
  generated_at: string
}

const { api } = useApi()

// Week offset relative to the current Persian week (0 = this week).
const weekOffset = ref(0)

const startParam = computed(() => {
  if (weekOffset.value === 0) return undefined
  // Shift by whole weeks from today; the backend snaps to Saturday itself.
  const base = new Date()
  base.setDate(base.getDate() + weekOffset.value * 7)
  return base.toISOString().slice(0, 10)
})

const { data, pending, error } = await useAsyncData<ScheduleResponse>(
  'weekly-schedule',
  () => api<ScheduleResponse>('/catalog/schedule/', {
    query: { days: 7, ...(startParam.value ? { start: startParam.value } : {}) },
  }),
  { watch: [startParam] },
)

const days = computed<ScheduleDay[]>(() => data.value?.days ?? [])
const total = computed(() => data.value?.total ?? 0)

// Active day tab: default to today when it's in range, else the first day.
const activeDate = ref<string | null>(null)
watch(days, (list) => {
  const first = list[0]
  if (!first) { activeDate.value = null; return }
  const today = list.find(d => d.is_today)
  const withContent = list.find(d => d.count > 0)
  const chosen = (today && today.count > 0) ? today : (withContent ?? today ?? first)
  activeDate.value = chosen.date
}, { immediate: true })

const activeDay = computed(() => days.value.find(d => d.date === activeDate.value) ?? null)

const jalaliParts = (iso: string) => {
  const date = new Date(`${iso}T00:00:00`)
  const day = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { day: 'numeric' }).format(date)
  const month = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { month: 'long' }).format(date)
  return { day, month }
}

const rangeLabel = computed(() => {
  if (!data.value) return ''
  const s = jalaliParts(data.value.start)
  const e = jalaliParts(data.value.end)
  return `${s.day} ${s.month} تا ${e.day} ${e.month}`
})

const weekTitle = computed(() => {
  if (weekOffset.value === 0) return 'این هفته'
  if (weekOffset.value === -1) return 'هفته گذشته'
  if (weekOffset.value === 1) return 'هفته آینده'
  return rangeLabel.value
})

function entryLink(entry: ScheduleEntry) {
  return entry.type === 'movie' ? `/movies/${entry.series_slug}` : `/series/${entry.series_slug}`
}

function episodeTag(entry: ScheduleEntry) {
  if (entry.type === 'movie') return 'فیلم'
  const s = entry.season_number ?? 0
  const e = entry.episode_number ?? 0
  return `فصل ${s.toLocaleString('fa-IR')} · قسمت ${e.toLocaleString('fa-IR')}`
}

useSeoMeta({
  title: 'جدول پخش هفتگی',
  description: 'برنامه پخش قسمت‌های جدید سریال‌ها و اکران فیلم‌های این هفته در روایتو؛ روزبه‌روز و بر اساس تاریخ واقعی پخش.',
})
</script>

<template>
  <div class="schedule-page page-section pb-14">
    <header class="sched-hero">
      <div class="sched-hero__glow" aria-hidden="true" />
      <div class="sched-hero__grid" aria-hidden="true" />

      <div class="sched-hero__content">
        <div class="sched-hero__copy">
          <span class="sched-hero__icon" aria-hidden="true">
            <CinematicIcon name="calendar" class="size-5" />
          </span>
          <div class="min-w-0">
            <p class="sched-hero__eyebrow">برنامه پخش</p>
            <h1 class="sched-hero__title">جدول پخش هفتگی</h1>
            <p class="sched-hero__desc">
              قسمت‌های تازهٔ سریال‌ها و اکران فیلم‌ها، روزبه‌روز و بر پایهٔ تاریخ واقعی پخش. بدون داده‌ی ساختگی.
            </p>
          </div>
        </div>

        <div class="sched-hero__nav" aria-label="پیمایش هفته">
          <button type="button" class="sched-hero__navbtn" aria-label="هفته قبل" @click="weekOffset -= 1">
            <CinematicIcon name="chevron-right" class="size-4" />
          </button>
          <div class="sched-hero__weekmeta">
            <strong>{{ weekTitle }}</strong>
            <span>{{ rangeLabel }}</span>
          </div>
          <button type="button" class="sched-hero__navbtn" aria-label="هفته بعد" @click="weekOffset += 1">
            <CinematicIcon name="chevron-left" class="size-4" />
          </button>
          <button
            v-if="weekOffset !== 0"
            type="button"
            class="sched-hero__today"
            @click="weekOffset = 0"
          >
            امروز
          </button>
        </div>
      </div>
    </header>

    <!-- Day strip -->
    <div v-if="days.length" class="sched-strip" role="tablist" aria-label="روزهای هفته">
      <button
        v-for="day in days"
        :key="day.date"
        type="button"
        role="tab"
        class="sched-strip__day"
        :class="[
          activeDate === day.date && 'sched-strip__day--active',
          day.is_today && 'sched-strip__day--today',
          !day.count && 'sched-strip__day--empty',
        ]"
        :aria-selected="activeDate === day.date"
        @click="activeDate = day.date"
      >
        <span class="sched-strip__weekday">{{ day.weekday_label }}</span>
        <span class="sched-strip__daynum">{{ jalaliParts(day.date).day }}</span>
        <span class="sched-strip__month">{{ jalaliParts(day.date).month }}</span>
        <span class="sched-strip__count tabular-nums">{{ day.count.toLocaleString('fa-IR') }}</span>
      </button>
    </div>

    <!-- Loading -->
    <div v-if="pending && !days.length" class="sched-list mt-6">
      <div v-for="index in 6" :key="index" class="skeleton-card h-24 rounded-2xl" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="sched-empty" role="status">
      <CinematicIcon name="calendar" class="size-7 text-muted" />
      <p>دریافت جدول پخش با خطا روبه‌رو شد. کمی بعد دوباره تلاش کنید.</p>
    </div>

    <!-- Content -->
    <section v-else-if="activeDay" class="sched-body" :aria-label="`پخش ${activeDay.weekday_label}`">
      <div class="sched-section-head">
        <h2>
          {{ activeDay.weekday_label }}
          <span class="sched-section-head__date">{{ jalaliParts(activeDay.date).day }} {{ jalaliParts(activeDay.date).month }}</span>
          <span v-if="activeDay.is_today" class="sched-section-head__badge">امروز</span>
        </h2>
        <p>{{ activeDay.count.toLocaleString('fa-IR') }} عنوان</p>
      </div>

      <div v-if="activeDay.entries.length" class="sched-list">
        <NuxtLink
          v-for="(entry, idx) in activeDay.entries"
          :key="`${entry.type}-${entry.series_slug}-${entry.season_number}-${entry.episode_number}-${idx}`"
          :to="entryLink(entry)"
          class="sched-card"
          :class="!entry.released && 'sched-card--upcoming'"
        >
          <div class="sched-card__poster">
            <img
              v-if="entry.poster_url"
              :src="entry.poster_url"
              :alt="entry.series_title"
              loading="lazy"
              decoding="async"
            >
            <span v-else class="sched-card__poster-fallback" aria-hidden="true">
              <CinematicIcon :name="entry.type === 'movie' ? 'movie' : 'series'" class="size-5" />
            </span>
          </div>

          <div class="sched-card__body">
            <div class="sched-card__titles">
              <h3 class="sched-card__title">{{ entry.series_title }}</h3>
              <p v-if="entry.series_original_title && entry.series_original_title !== entry.series_title" class="sched-card__subtitle">
                {{ entry.series_original_title }}
              </p>
            </div>

            <div class="sched-card__meta">
              <span class="sched-card__tag">{{ episodeTag(entry) }}</span>
              <span v-if="entry.episode_title && entry.type === 'episode'" class="sched-card__eptitle">{{ entry.episode_title }}</span>
            </div>

            <div class="sched-card__chips">
              <span v-if="entry.imdb_rating" class="sched-chip sched-chip--imdb">
                <CinematicIcon name="star" class="size-3" />
                {{ entry.imdb_rating }}
              </span>
              <span v-if="entry.is_dubbed" class="sched-chip">دوبله</span>
              <span v-if="entry.has_subtitle" class="sched-chip">زیرنویس</span>
              <span class="sched-chip sched-chip--state" :class="entry.released ? 'is-released' : 'is-upcoming'">
                {{ entry.released ? 'پخش‌شده' : 'به‌زودی' }}
              </span>
            </div>
          </div>

          <CinematicIcon name="chevron-left" class="sched-card__go size-4" />
        </NuxtLink>
      </div>

      <div v-else class="sched-empty" role="status">
        <CinematicIcon name="calendar" class="size-7 text-muted" />
        <p>برای این روز عنوانی در جدول پخش ثبت نشده است.</p>
      </div>
    </section>

    <div v-else-if="!total" class="sched-empty" role="status">
      <CinematicIcon name="calendar" class="size-7 text-muted" />
      <p>این هفته موردی برای نمایش در جدول پخش وجود ندارد.</p>
    </div>
  </div>
</template>

<style scoped>
.schedule-page {
  --sc-ink: var(--theme-text-primary);
  --sc-soft: var(--theme-text-secondary);
  --sc-muted: var(--theme-text-muted);
  --sc-line: color-mix(in srgb, var(--theme-border) 88%, transparent);
  --sc-fill: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
  --sc-surface: color-mix(in srgb, var(--theme-bg-surface) 92%, transparent);
  --sc-accent: var(--theme-accent, #fb2c5a);
}

/* Hero */
.sched-hero {
  position: relative;
  overflow: hidden;
  margin-bottom: 1.25rem;
  border: 1px solid var(--sc-line);
  border-radius: 1.35rem;
  background: linear-gradient(160deg, color-mix(in srgb, var(--theme-bg-elevated) 55%, transparent), var(--sc-surface));
  padding: clamp(1.1rem, 2.8vw, 1.75rem);
}

.sched-hero__glow {
  position: absolute;
  inset: auto -20% -45% 20%;
  height: 70%;
  background: radial-gradient(circle, color-mix(in srgb, var(--sc-accent) 16%, transparent), transparent 68%);
  pointer-events: none;
}

.sched-hero__grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(color-mix(in srgb, var(--sc-accent) 6%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--sc-accent) 6%, transparent) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(180deg, rgb(0 0 0 / 55%), transparent 88%);
  pointer-events: none;
}

.sched-hero__content {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

.sched-hero__copy {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
}

.sched-hero__icon {
  display: grid;
  width: 2.65rem;
  height: 2.65rem;
  flex: none;
  place-items: center;
  border-radius: 0.85rem;
  background: var(--sc-fill);
  color: var(--sc-accent);
  box-shadow: inset 0 0 0 1px var(--sc-line);
}

.sched-hero__eyebrow {
  color: var(--sc-muted);
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.sched-hero__title {
  margin-top: 0.2rem;
  color: var(--sc-ink);
  font-size: clamp(1.55rem, 4vw, 2.35rem);
  font-weight: 900;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.sched-hero__desc {
  margin-top: 0.55rem;
  max-width: 40rem;
  color: var(--sc-soft);
  font-size: 0.875rem;
  line-height: 1.8;
}

.sched-hero__nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sched-hero__navbtn {
  display: grid;
  width: 2.5rem;
  height: 2.5rem;
  flex: none;
  place-items: center;
  border-radius: 0.75rem;
  background: var(--sc-fill);
  color: var(--sc-ink);
  box-shadow: inset 0 0 0 1px var(--sc-line);
  transition: background-color 140ms ease, color 140ms ease;
}

.sched-hero__navbtn:hover {
  background: color-mix(in srgb, var(--sc-accent) 16%, var(--sc-fill));
  color: var(--sc-accent);
}

.sched-hero__weekmeta {
  display: flex;
  min-width: 8rem;
  flex-direction: column;
  align-items: center;
  line-height: 1.25;
  text-align: center;
}

.sched-hero__weekmeta strong {
  color: var(--sc-ink);
  font-size: 0.875rem;
  font-weight: 900;
}

.sched-hero__weekmeta span {
  color: var(--sc-muted);
  font-size: 0.75rem;
  font-weight: 700;
}

.sched-hero__today {
  border-radius: 0.7rem;
  background: var(--sc-accent);
  padding: 0.5rem 0.85rem;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 800;
}

/* Day strip */
.sched-strip {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(4.5rem, 1fr);
  gap: 0.4rem;
  overflow-x: auto;
  padding-bottom: 0.25rem;
  scrollbar-width: thin;
  -webkit-overflow-scrolling: touch;
}

.sched-strip__day {
  display: flex;
  min-height: 5.25rem;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.1rem;
  border-radius: 1rem;
  background: var(--sc-surface);
  padding: 0.6rem 0.35rem;
  box-shadow: inset 0 0 0 1px var(--sc-line);
  transition: background-color 150ms ease, box-shadow 150ms ease, transform 150ms ease;
}

.sched-strip__weekday {
  color: var(--sc-soft);
  font-size: 0.75rem;
  font-weight: 800;
}

.sched-strip__daynum {
  color: var(--sc-ink);
  font-size: 1.25rem;
  font-weight: 900;
  line-height: 1.1;
}

.sched-strip__month {
  color: var(--sc-muted);
  font-size: 0.75rem;
  font-weight: 700;
}

.sched-strip__count {
  margin-top: 0.15rem;
  border-radius: 999px;
  background: var(--sc-fill);
  padding: 0.05rem 0.5rem;
  color: var(--sc-soft);
  font-size: 0.75rem;
  font-weight: 800;
}

.sched-strip__day--empty { opacity: 0.62; }

.sched-strip__day--today {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--sc-accent) 55%, transparent);
}

.sched-strip__day--active {
  background: color-mix(in srgb, var(--sc-accent) 16%, var(--sc-surface));
  box-shadow: inset 0 0 0 1.5px var(--sc-accent);
  opacity: 1;
}

.sched-strip__day--active .sched-strip__daynum,
.sched-strip__day--active .sched-strip__weekday {
  color: var(--sc-accent);
}

/* Section head */
.sched-section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.4rem 1rem;
  margin: 1.5rem 0 0.85rem;
}

.sched-section-head h2 {
  display: inline-flex;
  align-items: baseline;
  gap: 0.5rem;
  color: var(--sc-ink);
  font-size: 1.05rem;
  font-weight: 900;
}

.sched-section-head__date {
  color: var(--sc-muted);
  font-size: 0.8rem;
  font-weight: 700;
}

.sched-section-head__badge {
  border-radius: 999px;
  background: var(--sc-accent);
  padding: 0.1rem 0.5rem;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 800;
}

.sched-section-head p {
  color: var(--sc-muted);
  font-size: 0.75rem;
  font-weight: 700;
}

/* Cards */
.sched-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.55rem;
}

.sched-card {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  border-radius: 1rem;
  background: var(--sc-surface);
  padding: 0.7rem;
  box-shadow: inset 0 0 0 1px var(--sc-line);
  transition: box-shadow 160ms ease, transform 160ms ease, background-color 160ms ease;
}

.sched-card--upcoming { opacity: 0.9; }

.sched-card__poster {
  position: relative;
  width: 3.25rem;
  height: 4.75rem;
  flex: none;
  overflow: hidden;
  border-radius: 0.6rem;
  background: var(--sc-fill);
  box-shadow: inset 0 0 0 1px var(--sc-line);
}

.sched-card__poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.sched-card__poster-fallback {
  display: grid;
  width: 100%;
  height: 100%;
  place-items: center;
  color: var(--sc-muted);
}

.sched-card__body {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.35rem;
}

.sched-card__title {
  overflow: hidden;
  color: var(--sc-ink);
  font-size: 0.9375rem;
  font-weight: 900;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sched-card__subtitle {
  overflow: hidden;
  color: var(--sc-muted);
  font-size: 0.75rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
  direction: ltr;
  text-align: right;
}

.sched-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.5rem;
}

.sched-card__tag {
  border-radius: 0.5rem;
  background: var(--sc-fill);
  padding: 0.15rem 0.5rem;
  color: var(--sc-soft);
  font-size: 0.75rem;
  font-weight: 800;
}

.sched-card__eptitle {
  overflow: hidden;
  color: var(--sc-muted);
  font-size: 0.75rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sched-card__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.sched-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  border-radius: 999px;
  background: var(--sc-fill);
  padding: 0.1rem 0.5rem;
  color: var(--sc-soft);
  font-size: 0.75rem;
  font-weight: 800;
  box-shadow: inset 0 0 0 1px var(--sc-line);
}

.sched-chip--imdb {
  color: #f5c518;
  background: color-mix(in srgb, #f5c518 12%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #f5c518 30%, transparent);
}

.sched-chip--state.is-released {
  color: var(--theme-success, #22c55e);
  background: color-mix(in srgb, var(--theme-success, #22c55e) 12%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-success, #22c55e) 28%, transparent);
}

.sched-chip--state.is-upcoming {
  color: var(--sc-accent);
  background: color-mix(in srgb, var(--sc-accent) 12%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--sc-accent) 28%, transparent);
}

.sched-card__go {
  flex: none;
  color: var(--sc-muted);
  transition: transform 160ms ease, color 160ms ease;
}

/* Empty / error */
.sched-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.65rem;
  margin-top: 1.5rem;
  border-radius: 1.15rem;
  background: var(--sc-surface);
  padding: 2.5rem 1rem;
  color: var(--sc-muted);
  font-size: 0.8125rem;
  font-weight: 700;
  box-shadow: inset 0 0 0 1px var(--sc-line);
  text-align: center;
}

@media (min-width: 640px) {
  .sched-hero__content {
    flex-direction: row;
    align-items: flex-end;
    justify-content: space-between;
  }

  .sched-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1024px) {
  .sched-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (hover: hover) and (pointer: fine) {
  .sched-card:hover {
    transform: translate3d(0, -0.1rem, 0);
    background: var(--sc-fill);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--sc-accent) 40%, transparent);
  }

  .sched-card:hover .sched-card__go {
    transform: translateX(-0.15rem);
    color: var(--sc-accent);
  }

  .sched-strip__day:hover {
    transform: translate3d(0, -0.1rem, 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .sched-card,
  .sched-card__go,
  .sched-strip__day,
  .sched-hero__navbtn {
    transition: none;
  }

  .sched-card:hover,
  .sched-strip__day:hover {
    transform: none;
  }
}
</style>
