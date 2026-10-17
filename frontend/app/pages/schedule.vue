<script setup lang="ts">
const { api } = useApi()

// 0 = the 7 days ending today; -1 = the 7 days before that, and so on.
const weekOffset = ref(0)

const endParam = computed(() => {
  if (weekOffset.value === 0) return undefined
  // The backend clamps to Tehran's today and never looks into the future.
  const base = new Date()
  base.setDate(base.getDate() + weekOffset.value * 7)
  return base.toISOString().slice(0, 10)
})

const { data, pending, error } = await useAsyncData<ScheduleResponse>(
  'weekly-schedule',
  () => api<ScheduleResponse>('/catalog/schedule/', {
    query: { days: 7, ...(endParam.value ? { end: endParam.value } : {}) },
  }),
  { watch: [endParam] },
)

const today = computed(() => data.value?.today ?? '')
const total = computed(() => data.value?.total ?? 0)
// Only days that have something to watch, in calendar order: the strip reads
// right-to-left like the week itself, today at its far (left) end.
const days = computed<ScheduleDay[]>(() => (data.value?.days ?? []).filter(d => d.count > 0))

const activeDate = ref<string | null>(null)
watch(days, (list) => {
  if (!list.some(d => d.date === activeDate.value)) activeDate.value = list[list.length - 1]?.date ?? null
}, { immediate: true })

const activeDay = computed(() => days.value.find(d => d.date === activeDate.value) ?? null)

const rangeLabel = computed(() => {
  if (!data.value) return ''
  const s = jalaliParts(data.value.start)
  const e = jalaliParts(data.value.end)
  return s.month === e.month ? `${s.day} تا ${e.day} ${e.month}` : `${s.day} ${s.month} تا ${e.day} ${e.month}`
})

function olderWeek() {
  weekOffset.value -= 1
  if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
}

const weekTitle = computed(() => (weekOffset.value === 0 ? 'هفتهٔ اخیر' : weekOffset.value === -1 ? 'هفتهٔ قبل' : rangeLabel.value))

useSeoMeta({
  title: 'جدول پخش هفتگی',
  description: 'قسمت‌های تازهٔ سریال‌ها و نسخهٔ دیجیتال فیلم‌هایی که این هفته پخش شده‌اند و همین حالا در روایتو آماده تماشا و دانلودند؛ روزبه‌روز و به وقت تهران.',
})
</script>

<template>
  <div class="schedule-page page-section pb-14">
    <header class="sched-head">
      <div class="min-w-0">
        <h1 class="sched-head__title">جدول پخش هفتگی</h1>
        <p class="sched-head__desc">
          قسمت‌ها و فیلم‌هایی که این هفته پخش شده‌اند و همین حالا در روایتو آماده تماشا و دانلودند.
        </p>
      </div>

      <nav class="sched-nav" aria-label="پیمایش هفته">
        <button type="button" class="sched-nav__btn" aria-label="هفتهٔ قبل" @click="weekOffset -= 1">
          <CinematicIcon name="chevron-right" class="size-4" />
        </button>
        <div class="sched-nav__meta">
          <strong>{{ weekTitle }}</strong>
          <span>{{ rangeLabel }}</span>
        </div>
        <button
          type="button"
          class="sched-nav__btn"
          aria-label="هفتهٔ بعد"
          :disabled="weekOffset === 0"
          @click="weekOffset += 1"
        >
          <CinematicIcon name="chevron-left" class="size-4" />
        </button>
      </nav>
    </header>

    <!-- Loading -->
    <div v-if="pending && !data" class="sched-grid mt-4" aria-hidden="true">
      <div v-for="index in 12" :key="index" class="skeleton-card aspect-[2/3] rounded-xl" />
    </div>

    <div v-else-if="error" class="sched-empty" role="status">
      <CinematicIcon name="calendar" class="size-7" />
      <p>جدول پخش باز نشد. کمی بعد دوباره امتحان کنید.</p>
    </div>

    <div v-else-if="!days.length" class="sched-empty" role="status">
      <CinematicIcon name="calendar" class="size-7" />
      <p>در این هفته هنوز قسمت یا فیلم تازه‌ای به روایتو اضافه نشده است.</p>
      <RippleButton v-if="weekOffset === 0" @click="weekOffset = -1">دیدن هفتهٔ قبل</RippleButton>
    </div>

    <template v-else>
      <ScrollStrip track-class="sched-days" role="tablist" label="روزهای هفته" :active-key="activeDate">
        <button
          v-for="day in days"
          :key="day.date"
          type="button"
          role="tab"
          class="sched-day"
          :class="{ 'is-active': activeDate === day.date }"
          :aria-selected="activeDate === day.date"
          @click="activeDate = day.date"
        >
          <span class="sched-day__name">{{ dayName(day, today) }}</span>
          <span class="sched-day__date">{{ jalaliParts(day.date).day }} {{ jalaliParts(day.date).month }}</span>
          <span class="sched-day__count tabular-nums">{{ day.count.toLocaleString('fa-IR') }}</span>
        </button>
      </ScrollStrip>

      <p class="sched-summary">
        {{ total.toLocaleString('fa-IR') }} عنوان تازه در این هفته، همه آماده تماشا و دانلود
      </p>

      <section v-if="activeDay" class="sched-grid" role="tabpanel" :aria-label="dayName(activeDay, today)">
        <ScheduleCard
          v-for="entry in activeDay.entries"
          :key="`${entry.type}-${entry.series_slug}-${entry.season_number}-${entry.episode_number}`"
          :entry="entry"
        />
      </section>

      <div class="sched-more">
        <RippleButton @click="olderWeek">پخش‌های هفتهٔ قبل</RippleButton>
      </div>
    </template>

    <p class="sched-note">
      تاریخ هر مورد، روز رسمی پخش آن قسمت (برای فیلم‌ها روز انتشار نسخهٔ دیجیتال) به وقت تهران است. هر قسمت همان روزی که لینک‌هایش آماده شود به این جدول اضافه می‌شود.
    </p>
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
  /* The روایتو green accent (mint on dark, pine on light). */
  --sc-warm: var(--theme-accent-primary);
  --sc-warm-ink: var(--theme-on-accent);
  --sc-warm-soft: color-mix(in srgb, var(--sc-warm) 14%, transparent);
}


/* Header */
.sched-head {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.sched-head__title {
  color: var(--sc-ink);
  font-size: clamp(1.5rem, 4vw, 2.1rem);
  font-weight: 900;
  line-height: 1.2;
  text-wrap: balance;
}

.sched-head__desc {
  margin-top: 0.45rem;
  max-width: 38rem;
  color: var(--sc-soft);
  font-size: 0.875rem;
  line-height: 1.8;
}

.sched-nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sched-nav__btn {
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

.sched-nav__btn:disabled {
  cursor: default;
  opacity: 0.35;
}

.sched-nav__btn:focus-visible,
.sched-day:focus-visible {
  outline: 2px solid var(--sc-warm);
  outline-offset: 2px;
}

.sched-nav__meta {
  display: flex;
  min-width: 7.5rem;
  flex-direction: column;
  align-items: center;
  line-height: 1.3;
}

.sched-nav__meta strong {
  color: var(--sc-ink);
  font-size: 0.875rem;
  font-weight: 900;
}

.sched-nav__meta span {
  color: var(--sc-muted);
  font-size: 0.75rem;
  font-weight: 700;
}

/* Day tabs */
:deep(.sched-days) {
  display: flex;
  gap: 0.45rem;
  padding-bottom: 0.15rem;
}

.sched-day {
  display: inline-flex;
  min-height: 2.9rem;
  flex: none;
  align-items: center;
  gap: 0.45rem;
  border-radius: 0.85rem;
  background: var(--sc-fill);
  padding: 0 0.85rem;
  color: var(--sc-soft);
  font-size: 0.8125rem;
  font-weight: 700;
  box-shadow: inset 0 0 0 1px var(--sc-line);
  transition: background-color 150ms ease, color 150ms ease;
}

.sched-day__name {
  color: var(--sc-ink);
  font-weight: 900;
}

.sched-day__date { color: var(--sc-muted); }

.sched-day__count {
  display: grid;
  min-width: 1.4rem;
  height: 1.4rem;
  place-items: center;
  border-radius: 999px;
  background: var(--sc-warm-soft);
  padding: 0 0.35rem;
  color: var(--sc-warm);
  font-size: 0.75rem;
  font-weight: 900;
}

.sched-day.is-active {
  background: var(--sc-warm);
  box-shadow: none;
}

.sched-day.is-active .sched-day__name,
.sched-day.is-active .sched-day__date { color: var(--sc-warm-ink); }

.sched-day.is-active .sched-day__count {
  background: color-mix(in srgb, var(--sc-warm-ink) 16%, transparent);
  color: var(--sc-warm-ink);
}

.sched-summary {
  margin: 0.9rem 0 0.85rem;
  color: var(--sc-muted);
  font-size: 0.8125rem;
  font-weight: 700;
}

/* Poster grid */
.sched-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

@media (min-width: 520px) {
  .sched-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

/* Empty / error */
.sched-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  border-radius: 1.1rem;
  background: var(--sc-surface);
  padding: 2.75rem 1rem;
  color: var(--sc-muted);
  font-size: 0.875rem;
  font-weight: 700;
  text-align: center;
  box-shadow: inset 0 0 0 1px var(--sc-line);
}

.sched-more {
  display: flex;
  justify-content: center;
  margin-top: 1.75rem;
}

.sched-note {
  max-width: 65ch;
  margin-top: 1.75rem;
  color: var(--sc-muted);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.9;
}

@media (min-width: 640px) {
  .sched-head {
    flex-direction: row;
    align-items: flex-end;
    justify-content: space-between;
  }
}

@media (min-width: 768px) {
  .sched-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}

@media (min-width: 1024px) {
  .sched-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}

/* From 1280px the grid follows the site-wide column count, so wide screens
   get more cards per row instead of stretched ones. */
@media (min-width: 1280px) {
  .sched-grid { grid-template-columns: repeat(var(--rail-columns), minmax(0, 1fr)); }
}

@media (hover: hover) and (pointer: fine) {
  .sched-nav__btn:not(:disabled):hover { color: var(--sc-warm); }
  .sched-day:not(.is-active):hover { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--sc-warm) 45%, transparent); }
}

@media (prefers-reduced-motion: reduce) {
  .sched-day,
  .sched-nav__btn { transition: none; }
}
</style>
