<script setup lang="ts">
/**
 * Home «جدول پخش این هفته»: the week's releases (real TMDB air dates, Tehran
 * time) that are on روایتو right now — nothing that is still coming or still
 * being fetched. Days read right-to-left in calendar order, today last; the
 * full week lives on /schedule.
 */
const { api } = useApi()

const { data, pending } = useLazyAsyncData<ScheduleResponse>(
  'home-schedule',
  () => api<ScheduleResponse>('/catalog/schedule/', { query: { days: 7 } }),
  { server: false },
)

const today = computed(() => data.value?.today ?? '')
const total = computed(() => data.value?.total ?? 0)
const days = computed<ScheduleDay[]>(() => (data.value?.days ?? []).filter(d => d.count > 0))

const activeDate = ref<string | null>(null)
watch(days, (list) => {
  if (!list.some(d => d.date === activeDate.value)) activeDate.value = list[list.length - 1]?.date ?? null
}, { immediate: true })

const activeDay = computed(() => days.value.find(d => d.date === activeDate.value) ?? null)

const eyebrow = computed(() => `${total.value.toLocaleString('fa-IR')} عنوان تازه در هفتهٔ اخیر`)
</script>

<template>
  <section v-if="pending || total > 0" class="content-section home-sched" aria-labelledby="home-sched-title">
    <SectionHeader
      title="جدول پخش این هفته"
      :eyebrow="total ? eyebrow : 'به وقت تهران'"
      description="قسمت‌های تازه و فیلم‌هایی که این هفته پخش شده‌اند و همین حالا آماده تماشا و دانلودند."
      href="/schedule"
      link-label="جدول کامل"
      icon="schedule"
      dark
    />

    <div v-if="pending && !days.length" class="home-sched__skeleton" aria-hidden="true">
      <div class="skeleton-card h-11 rounded-xl" />
      <div class="flex gap-2.5 overflow-hidden">
        <div v-for="i in 6" :key="i" class="skeleton-card aspect-[2/3] w-32 shrink-0 rounded-xl sm:w-36" />
      </div>
    </div>

    <template v-else>
      <ScrollStrip track-class="home-sched__days" role="tablist" label="روزهای این هفته" :active-key="activeDate">
        <button
          v-for="day in days"
          :key="day.date"
          type="button"
          role="tab"
          class="home-sched__day"
          :class="{ 'is-active': activeDate === day.date }"
          :aria-selected="activeDate === day.date"
          @click="activeDate = day.date"
        >
          <span class="home-sched__dayname">{{ dayName(day, today) }}</span>
          <span class="home-sched__daycount tabular-nums">{{ day.count.toLocaleString('fa-IR') }}</span>
        </button>
      </ScrollStrip>

      <ScrollStrip
        v-if="activeDay"
        :key="activeDay.date"
        track-class="home-sched__rail"
        role="tabpanel"
        :label="dayName(activeDay, today)"
      >
        <ScheduleCard
          v-for="entry in activeDay.entries"
          :key="`${entry.type}-${entry.series_slug}-${entry.season_number}-${entry.episode_number}`"
          :entry="entry"
          class="home-sched__card"
        />
      </ScrollStrip>

      <div class="home-sched__cta">
        <RippleButton to="/schedule">جدول کامل پخش هفته</RippleButton>
      </div>
    </template>
  </section>
</template>

<style scoped>
.home-sched {
  --hs-line: color-mix(in srgb, var(--theme-border) 88%, transparent);
  --hs-fill: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
  /* The روایتو green accent (mint on dark, pine on light). */
  --hs-accent: var(--theme-accent-primary);
  --hs-accent-ink: var(--theme-on-accent);
}


.home-sched__skeleton {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

/* Day chips (the track lives inside ScrollStrip, hence :deep) */
.home-sched :deep(.home-sched__days) {
  display: flex;
  gap: 0.4rem;
  margin-bottom: 0.85rem;
  padding-bottom: 0.1rem;
}

.home-sched__day {
  display: inline-flex;
  min-height: 2.75rem;
  flex: none;
  align-items: center;
  gap: 0.4rem;
  border-radius: 0.8rem;
  background: var(--hs-fill);
  padding: 0 0.8rem;
  color: var(--theme-text-secondary);
  font-size: 0.8125rem;
  font-weight: 800;
  box-shadow: inset 0 0 0 1px var(--hs-line);
  transition: background-color 150ms ease, color 150ms ease, box-shadow 150ms ease;
}

.home-sched__day.is-active {
  background: var(--hs-accent);
  color: var(--hs-accent-ink);
  box-shadow: none;
}

.home-sched__day:focus-visible {
  outline: 2px solid var(--hs-accent);
  outline-offset: 2px;
}

.home-sched__daycount {
  display: grid;
  min-width: 1.25rem;
  height: 1.25rem;
  place-items: center;
  border-radius: 999px;
  background: color-mix(in srgb, currentColor 14%, transparent);
  padding: 0 0.3rem;
  font-size: 0.6875rem;
}

.home-sched__cta {
  display: flex;
  justify-content: center;
  margin-top: 1rem;
}

/* Rail */
.home-sched :deep(.home-sched__rail) {
  display: flex;
  gap: 0.65rem;
  scroll-snap-type: x proximity;
  padding-bottom: 0.4rem;
}

.home-sched__card {
  width: 10rem;
  flex: none;
  scroll-snap-align: start;
}

@media (min-width: 640px) {
  .home-sched__card { width: 11rem; }
}

@media (min-width: 1280px) {
  .home-sched__card { width: 11.5rem; }
}

@media (hover: hover) and (pointer: fine) {
  .home-sched__day:not(.is-active):hover { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--hs-accent) 45%, transparent); }
}

@media (prefers-reduced-motion: reduce) {
  .home-sched__day { transition: none; }
}
</style>
