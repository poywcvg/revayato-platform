<script setup lang="ts">
import { formatWatchDuration, useWatchTime } from '~/composables/useWatchTime'

const { stats, loading, refreshRemote } = useWatchTime()
const { continueWatching, entries } = useWatchProgress()
const { catalog } = useCatalog()

const displayHours = ref(0)
const displayMinutes = ref(0)
const ringVisible = ref(false)

const headline = computed(() => formatWatchDuration(stats.value.hours, stats.value.minutes))
const weekHeadline = computed(() =>
  formatWatchDuration(stats.value.week_hours_part, stats.value.week_minutes_part),
)

const weekGoalRatio = computed(() => {
  const goal = Math.max(1, stats.value.weekly_goal_minutes || 300)
  return Math.min(1, stats.value.week_minutes / goal)
})

const ringDash = computed(() => {
  const circumference = 2 * Math.PI * 54
  return {
    circumference,
    offset: circumference * (1 - weekGoalRatio.value),
  }
})

const storyLine = computed(() => {
  const total = stats.value.total_minutes
  if (total < 1) {
    return 'هنوز ساعتی روی پرده ثبت نشده. اولین پخش، قلاب تماشایت را می‌سازد.'
  }
  const films = stats.value.equivalents.find(item => item.id === 'films')
  const nights = stats.value.equivalents.find(item => item.id === 'nights')
  if (films && films.value >= 1) {
    return `زمان تماشایت معادل حدود ${films.display} فیلم سینمایی است — انگار ${nights?.display || '۰'} شب کامل پای پرده نشسته‌ای.`
  }
  return stats.value.milestone.blurb
})

const metaBits = computed(() => [
  { label: 'عنوان شروع‌شده', value: stats.value.titles_started },
  { label: 'تمام‌شده', value: stats.value.titles_completed },
  { label: 'نیمه‌کاره', value: stats.value.titles_in_progress },
])

function animateCount(targetHours: number, targetMinutes: number) {
  const start = performance.now()
  const duration = 900
  const fromH = displayHours.value
  const fromM = displayMinutes.value
  const tick = (now: number) => {
    const t = Math.min(1, (now - start) / duration)
    const eased = 1 - (1 - t) ** 3
    displayHours.value = Math.round(fromH + (targetHours - fromH) * eased)
    displayMinutes.value = Math.round(fromM + (targetMinutes - fromM) * eased)
    if (t < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

function seedFromProgress() {
  const { recordProgress } = useWatchTime()
  const byKey = new Map(catalog.value.map(item => [`${item.type}:${item.id}`, item]))
  for (const entry of entries.value) {
    const item = byKey.get(`${entry.content_type}:${entry.object_id}`)
    if (!item) continue
    recordProgress(item, entry.progress_percent)
  }
  for (const item of continueWatching.value) {
    if (item.progress_percent > 1) recordProgress(item, item.progress_percent)
  }
}

onMounted(async () => {
  seedFromProgress()
  await refreshRemote()
  ringVisible.value = true
  animateCount(stats.value.hours, stats.value.minutes)
})

watch(
  () => [stats.value.hours, stats.value.minutes] as const,
  ([h, m]) => {
    if (import.meta.client) animateCount(h, m)
  },
)
</script>

<template>
  <section id="watch-time" class="watch-time-story content-section scroll-under-header" aria-labelledby="watch-time-title">
    <div class="watch-time-story__stage">
      <div class="watch-time-story__glow" aria-hidden="true" />
      <div class="watch-time-story__reel" aria-hidden="true">
        <span v-for="n in 8" :key="n" class="watch-time-story__perf" />
      </div>

      <div class="watch-time-story__grid">
        <div class="watch-time-story__main">
          <p class="watch-time-story__eyebrow">
            <CinematicIcon name="clock" class="size-4" />
            ساعت تماشای تو
          </p>
          <h2 id="watch-time-title" class="watch-time-story__title">
            <span class="watch-time-story__digits tabular-nums">
              <template v-if="displayHours > 0 || displayMinutes > 0">
                <span v-if="displayHours > 0">
                  <span class="watch-time-story__num">{{ displayHours.toLocaleString('fa-IR') }}</span>
                  <span class="watch-time-story__unit">ساعت</span>
                </span>
                <span v-if="displayHours > 0 && displayMinutes > 0" class="watch-time-story__and">و</span>
                <span v-if="displayMinutes > 0 || displayHours === 0">
                  <span class="watch-time-story__num">{{ displayMinutes.toLocaleString('fa-IR') }}</span>
                  <span class="watch-time-story__unit">دقیقه</span>
                </span>
              </template>
              <template v-else>
                <span class="watch-time-story__num">۰</span>
                <span class="watch-time-story__unit">دقیقه</span>
              </template>
            </span>
          </h2>
          <p class="watch-time-story__story">{{ storyLine }}</p>

          <div class="watch-time-story__milestone">
            <span class="watch-time-story__badge">{{ stats.milestone.label }}</span>
            <p v-if="stats.milestone.minutes_to_next != null" class="watch-time-story__next">
              تا «{{ stats.milestone.next_label }}» فقط
              {{ stats.milestone.minutes_to_next.toLocaleString('fa-IR') }} دقیقه مانده.
            </p>
            <p v-else class="watch-time-story__next">{{ stats.milestone.blurb }}</p>
          </div>
        </div>

        <div class="watch-time-story__week" aria-label="تماشای این هفته">
          <div class="watch-time-story__ring-wrap">
            <svg class="watch-time-story__ring" viewBox="0 0 120 120" aria-hidden="true">
              <circle class="watch-time-story__ring-track" cx="60" cy="60" r="54" />
              <circle
                class="watch-time-story__ring-progress"
                cx="60"
                cy="60"
                r="54"
                :stroke-dasharray="ringDash.circumference"
                :stroke-dashoffset="ringVisible ? ringDash.offset : ringDash.circumference"
              />
            </svg>
            <div class="watch-time-story__ring-label">
              <p class="text-[10px] font-black text-muted">این هفته</p>
              <p class="mt-0.5 text-xs font-black tabular-nums text-ink sm:text-sm">{{ weekHeadline }}</p>
            </div>
          </div>
          <p class="watch-time-story__goal">
            هدف سبک هفته:
            {{ (stats.weekly_goal_minutes / 60).toLocaleString('fa-IR') }} ساعت
            <span class="text-muted">· {{ Math.round(weekGoalRatio * 100).toLocaleString('fa-IR') }}٪</span>
          </p>
        </div>
      </div>

      <div class="watch-time-story__equivalents" aria-label="معادل‌های خلاقانه">
        <div
          v-for="item in stats.equivalents"
          :key="item.id"
          class="watch-time-story__eq"
        >
          <p class="watch-time-story__eq-value tabular-nums">{{ item.display }}</p>
          <p class="watch-time-story__eq-label">{{ item.label }}</p>
        </div>
      </div>

      <dl class="watch-time-story__meta">
        <div v-for="bit in metaBits" :key="bit.label" class="watch-time-story__meta-item">
          <dt>{{ bit.label }}</dt>
          <dd class="tabular-nums">{{ bit.value.toLocaleString('fa-IR') }}</dd>
        </div>
        <div v-if="loading" class="watch-time-story__meta-item watch-time-story__meta-item--soft">
          <dt>همگام‌سازی</dt>
          <dd>…</dd>
        </div>
      </dl>

      <p class="watch-time-story__footnote" aria-hidden="false">
        {{ headline === 'هنوز صفر' ? 'با اولین پخش، شمارنده زنده می‌شود.' : `جمع ثبت‌شده: ${headline}` }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.watch-time-story__stage {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  width: 100%;
  max-width: 100%;
  border-radius: 1.15rem;
  border: 1px solid var(--theme-border);
  background:
    radial-gradient(ellipse 80% 60% at 100% 0%, rgb(var(--palette-sand-rgb) / 14%), transparent 55%),
    radial-gradient(ellipse 70% 50% at 0% 100%, rgb(var(--palette-mid-rgb) / 12%), transparent 50%),
    linear-gradient(165deg, var(--theme-bg-elevated), var(--theme-bg-soft));
  padding: 1rem 0.95rem 0.95rem;
}

@media (min-width: 640px) {
  .watch-time-story__stage {
    border-radius: 1.5rem;
    padding: 1.75rem 1.75rem 1.35rem;
  }
}

.watch-time-story__glow {
  position: absolute;
  inset: auto -20% -40% 40%;
  height: 14rem;
  background: radial-gradient(circle, rgb(var(--palette-sand-rgb) / 18%), transparent 70%);
  pointer-events: none;
  z-index: 0;
  animation: watch-time-breathe 7s ease-in-out infinite;
}

.watch-time-story__reel {
  position: absolute;
  top: 0;
  inset-inline: 0;
  display: flex;
  gap: 0.45rem;
  padding: 0.35rem 0.65rem;
  opacity: 0.3;
  z-index: 0;
  pointer-events: none;
}

.watch-time-story__perf {
  width: 0.45rem;
  height: 0.55rem;
  border-radius: 0.12rem;
  background: color-mix(in srgb, var(--theme-text-muted) 55%, transparent);
  animation: watch-time-perf 2.8s linear infinite;
}

.watch-time-story__perf:nth-child(odd) {
  animation-delay: -1.2s;
}

.watch-time-story__grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.75rem 0.85rem;
  margin-top: 0.65rem;
}

@media (min-width: 768px) {
  .watch-time-story__grid {
    align-items: center;
    gap: 2rem;
  }
}

.watch-time-story__main {
  min-width: 0;
}

.watch-time-story__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
  font-size: 0.72rem;
  font-weight: 900;
  color: var(--theme-accent-primary);
}

.watch-time-story__title {
  margin: 0.45rem 0 0;
  line-height: 1.15;
}

.watch-time-story__digits {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 0.4rem;
}

.watch-time-story__num {
  font-size: clamp(1.85rem, 9vw, 3.6rem);
  font-weight: 900;
  letter-spacing: -0.03em;
  color: var(--theme-text-primary);
}

.watch-time-story__unit {
  font-size: clamp(0.85rem, 3.2vw, 1.25rem);
  font-weight: 800;
  color: var(--theme-text-secondary);
}

.watch-time-story__and {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--theme-text-muted);
}

.watch-time-story__story {
  margin: 0.7rem 0 0;
  max-width: 36rem;
  font-size: 0.82rem;
  line-height: 1.8;
  color: var(--theme-text-secondary);
}

@media (min-width: 640px) {
  .watch-time-story__story {
    font-size: 0.92rem;
    line-height: 1.85;
  }
}

.watch-time-story__milestone {
  margin-top: 0.85rem;
}

.watch-time-story__badge {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  border-radius: 0.65rem;
  background: color-mix(in srgb, var(--theme-accent-primary) 14%, transparent);
  color: var(--theme-accent-primary);
  padding: 0.28rem 0.65rem;
  font-size: 0.7rem;
  font-weight: 900;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-accent-primary) 28%, transparent);
}

.watch-time-story__next {
  margin: 0.4rem 0 0;
  font-size: 0.75rem;
  line-height: 1.65;
  color: var(--theme-text-muted);
}

.watch-time-story__week {
  display: grid;
  justify-items: center;
  gap: 0.45rem;
  width: 5.75rem;
}

@media (min-width: 640px) {
  .watch-time-story__week {
    width: auto;
    gap: 0.65rem;
  }
}

.watch-time-story__ring-wrap {
  position: relative;
  width: 5.5rem;
  height: 5.5rem;
}

@media (min-width: 640px) {
  .watch-time-story__ring-wrap {
    width: 7.5rem;
    height: 7.5rem;
  }
}

.watch-time-story__ring {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.watch-time-story__ring-track,
.watch-time-story__ring-progress {
  fill: none;
  stroke-width: 7;
}

.watch-time-story__ring-track {
  stroke: color-mix(in srgb, var(--theme-border) 90%, transparent);
}

.watch-time-story__ring-progress {
  stroke: var(--theme-accent-primary);
  stroke-linecap: round;
  transition: stroke-dashoffset 1.1s cubic-bezier(0.22, 1, 0.36, 1);
}

.watch-time-story__ring-label {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  text-align: center;
  padding: 0.35rem;
}

.watch-time-story__goal {
  margin: 0;
  font-size: 0.62rem;
  font-weight: 700;
  line-height: 1.45;
  color: var(--theme-text-secondary);
  text-align: center;
}

@media (min-width: 640px) {
  .watch-time-story__goal {
    font-size: 0.72rem;
  }
}

.watch-time-story__equivalents {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.45rem;
  margin-top: 1rem;
  padding-top: 0.9rem;
  border-top: 1px solid color-mix(in srgb, var(--theme-border) 80%, transparent);
}

@media (min-width: 640px) {
  .watch-time-story__equivalents {
    gap: 0.65rem;
    margin-top: 1.35rem;
    padding-top: 1.1rem;
  }
}

.watch-time-story__eq {
  min-width: 0;
}

.watch-time-story__eq-value {
  margin: 0;
  font-size: clamp(1rem, 4.2vw, 1.45rem);
  font-weight: 900;
  color: var(--theme-text-primary);
}

.watch-time-story__eq-label {
  margin: 0.15rem 0 0;
  font-size: 0.62rem;
  line-height: 1.45;
  color: var(--theme-text-muted);
}

@media (min-width: 640px) {
  .watch-time-story__eq-label {
    font-size: 0.68rem;
    line-height: 1.5;
  }
}

.watch-time-story__meta {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 1rem;
  margin: 0.85rem 0 0;
}

.watch-time-story__meta-item {
  display: flex;
  align-items: baseline;
  gap: 0.35rem;
}

.watch-time-story__meta-item dt {
  font-size: 0.65rem;
  color: var(--theme-text-muted);
}

.watch-time-story__meta-item dd {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 900;
  color: var(--theme-text-primary);
}

.watch-time-story__meta-item--soft dd {
  color: var(--theme-text-muted);
}

.watch-time-story__footnote {
  position: relative;
  z-index: 1;
  margin: 0.7rem 0 0;
  font-size: 0.65rem;
  color: color-mix(in srgb, var(--theme-text-muted) 85%, transparent);
}

@keyframes watch-time-breathe {
  0%, 100% { opacity: 0.55; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-6px); }
}

@keyframes watch-time-perf {
  0%, 100% { opacity: 0.25; }
  50% { opacity: 0.7; }
}

@media (prefers-reduced-motion: reduce) {
  .watch-time-story__glow,
  .watch-time-story__perf,
  .watch-time-story__ring-progress {
    animation: none;
    transition: none;
  }
}
</style>
