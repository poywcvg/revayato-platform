<script setup lang="ts">
const { insight, recommendations, pending, error, analyze } = useBehaviorInsight(6)

const confidence = computed(() => Math.round(Number(insight.value?.confidence || 0) * 100))
const confidenceLabel = computed(() => {
  if (confidence.value >= 70) return 'شناخت دقیق'
  if (confidence.value >= 35) return 'در حال شناخت بهتر'
  return 'شروع یادگیری'
})

const playbackLabel = computed(() => {
  const mode = insight.value?.taste_summary?.inferred_playback
  if (mode === 'dubbed') return 'دوبله فارسی'
  if (mode === 'subtitle') return 'زیرنویس فارسی'
  return 'ترکیبی / هر دو'
})

// Strength bars: when the backend reports a raw score use it; otherwise rank
// the genres relatively so the bars still communicate a preference ordering.
const tasteBars = computed(() => {
  const genres = insight.value?.taste_summary?.top_genres || []
  if (!genres.length) return []
  const withScore = genres
    .map(genre => ({ slug: genre.slug, title: genre.title, score: Number(genre.score || 0) }))
    .filter(item => item.score > 0)
  if (withScore.length === genres.length) {
    const max = Math.max(...withScore.map(item => item.score))
    return withScore
      .sort((left, right) => right.score - left.score)
      .map(item => ({ ...item, strength: max ? Math.round((item.score / max) * 100) : 0 }))
  }
  const ranked = [...genres].map((genre, index) => ({
    slug: genre.slug,
    title: genre.title,
    score: 0,
    strength: Math.round((100 * (genres.length - index)) / genres.length),
  }))
  return ranked
})

onMounted(analyze)
</script>

<template>
  <section id="behavior-insight" class="content-section scroll-under-header" aria-labelledby="behavior-insight-title">
    <div class="ai-insight">
      <div class="ai-insight__head">
        <span class="ai-insight__icon"><CinematicIcon name="sparkles" class="size-6" /></span>
        <div class="min-w-0 flex-1">
          <p class="text-xs font-black text-brand">تحلیل هوشمند رفتار تماشا</p>
          <h2 id="behavior-insight-title" class="mt-1 text-xl font-black text-ink sm:text-2xl">سلیقه‌ات را بهتر بشناس</h2>
          <p class="mt-1 text-xs leading-6 text-muted">فقط از جست‌وجوها، پسندها و سابقه تماشای همین حساب برای پیشنهاد عناوین موجود در روایتو استفاده می‌شود.</p>
        </div>
        <button type="button" class="ui-secondary-button min-h-11 shrink-0 px-3 text-xs" :disabled="pending" @click="analyze">
          <CinematicIcon name="refresh" class="size-4" :class="pending && 'animate-spin'" />
          {{ insight ? 'تحلیل دوباره' : 'شروع تحلیل' }}
        </button>
      </div>

      <div v-if="pending && !insight" class="mt-5 grid gap-3" aria-live="polite">
        <div class="skeleton-card h-24" /><div class="skeleton-card h-20" />
        <p class="text-center text-xs font-bold text-muted">در حال بررسی الگوی تماشای تو…</p>
      </div>
      <div v-else-if="error && !insight" class="mt-5 rounded-2xl bg-red-500/8 p-4 ring-1 ring-red-500/20" role="alert">
        <p class="text-sm font-bold text-red-300">{{ error }}</p>
        <button type="button" class="ui-ghost-button mt-3 min-h-10 text-xs" @click="analyze">تلاش دوباره</button>
      </div>
      <template v-else-if="insight">
        <div class="ai-insight__metrics">
          <div><strong>{{ confidence.toLocaleString('fa-IR') }}٪</strong><span>{{ confidenceLabel }}</span></div>
          <div><strong>{{ insight.signals_used.toLocaleString('fa-IR') }}</strong><span>نشانه رفتاری</span></div>
          <div><strong>{{ insight.taste_summary?.completed_count?.toLocaleString('fa-IR') || '۰' }}</strong><span>عنوان کامل‌شده</span></div>
        </div>

        <div v-if="tasteBars.length" class="ai-insight__taste">
          <div class="flex items-center justify-between gap-3">
            <p class="flex items-center gap-1.5 text-xs font-black text-brand">
              <CinematicIcon name="map" class="size-4" />نقشه سلیقه
            </p>
            <span class="inline-flex items-center gap-1 rounded-full bg-elevated px-2.5 py-1 text-[10px] font-bold text-secondary ring-1 ring-line">
              <CinematicIcon name="play" class="size-3" />{{ playbackLabel }}
            </span>
          </div>
          <div class="mt-3 grid gap-2.5">
            <div v-for="bar in tasteBars" :key="bar.slug" class="ai-taste-bar">
              <span class="ai-taste-bar__label">{{ bar.title }}</span>
              <span class="ai-taste-bar__track" aria-hidden="true">
                <span class="ai-taste-bar__fill" :style="{ width: `${bar.strength}%` }" />
              </span>
              <span class="ai-taste-bar__value tabular-nums">{{ bar.strength.toLocaleString('fa-IR') }}</span>
            </div>
          </div>
        </div>

        <div class="ai-insight__message">
          <div class="flex items-center gap-2 text-xs font-black text-brand"><CinematicIcon name="sparkles" class="size-4" />جمع‌بندی دستیار روایتو</div>
          <p class="mt-3 whitespace-pre-line text-sm leading-8 text-secondary">{{ insight.message }}</p>
          <p v-if="!insight.ai_available" class="mt-3 text-[11px] leading-5 text-muted">سرویس زبانی موقتاً در دسترس نبود؛ این جمع‌بندی با موتور پیشنهاد رفتارمحور روایتو ساخته شده است.</p>
        </div>

        <div v-if="recommendations.length" class="mt-5">
          <h3 class="text-sm font-black text-ink">انتخاب‌های پیشنهادی بر اساس این تحلیل</h3>
          <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <NuxtLink
              v-for="entry in recommendations"
              :key="`${entry.item.type}-${entry.item.id}`"
              :to="`/${entry.item.type === 'movie' ? 'movies' : 'series'}/${entry.item.slug}`"
              class="ai-pick"
            >
              <NuxtImg :src="entry.item.poster_url" :alt="`پوستر ${entry.item.title}`" class="aspect-[2/3] w-14 shrink-0 rounded-xl object-cover" loading="lazy" />
              <span class="min-w-0">
                <strong class="block truncate text-xs font-black text-ink">{{ entry.item.title }}</strong>
                <small class="mt-1 line-clamp-2 block leading-5 text-muted">{{ entry.reason }}</small>
              </span>
            </NuxtLink>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.ai-insight { overflow: hidden; border: 1px solid color-mix(in srgb, var(--theme-accent-primary) 28%, var(--theme-border)); border-radius: 1.5rem; background: linear-gradient(145deg, color-mix(in srgb, var(--theme-accent-primary) 7%, var(--theme-bg-surface)), var(--theme-bg-surface)); padding: 1rem; }
.ai-insight__head { display: flex; flex-wrap: wrap; align-items: flex-start; gap: .8rem; }
.ai-insight__icon { display: grid; width: 3rem; height: 3rem; flex: none; place-items: center; border-radius: 1rem; background: color-mix(in srgb, var(--theme-accent-primary) 16%, transparent); color: var(--theme-accent-primary); }
.ai-insight__metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; margin-top: 1.25rem; }
.ai-insight__metrics div { border-radius: 1rem; background: var(--theme-bg-elevated); padding: .8rem; text-align: center; }
.ai-insight__metrics strong,.ai-insight__metrics span { display: block; }
.ai-insight__metrics strong { color: var(--theme-text-primary); font-size: 1rem; font-weight: 900; }
.ai-insight__metrics span { margin-top: .2rem; color: var(--theme-text-muted); font-size: .62rem; }

.ai-insight__taste { margin-top: 1rem; border-radius: 1.15rem; background: color-mix(in srgb, var(--theme-bg-canvas) 75%, transparent); padding: .9rem 1rem; box-shadow: inset 0 0 0 1px var(--theme-border); }
.ai-taste-bar { display: grid; grid-template-columns: minmax(4.5rem, 7rem) minmax(0, 1fr) 2rem; align-items: center; gap: .5rem; }
.ai-taste-bar__label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--theme-text-secondary); font-size: .7rem; font-weight: 700; }
.ai-taste-bar__track { height: .5rem; border-radius: 999px; background: color-mix(in srgb, var(--theme-text-muted) 22%, transparent); overflow: hidden; }
.ai-taste-bar__fill { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, color-mix(in srgb, var(--theme-accent-primary) 70%, white), var(--theme-accent-primary)); transition: width 700ms cubic-bezier(.22, 1, .36, 1); }
.ai-taste-bar__value { text-align: left; color: var(--theme-text-muted); font-size: .62rem; }

.ai-insight__message { margin-top: 1rem; border-radius: 1.15rem; background: color-mix(in srgb, var(--theme-bg-canvas) 75%, transparent); padding: 1rem; box-shadow: inset 0 0 0 1px var(--theme-border); }
.ai-pick { display: flex; min-width: 0; align-items: center; gap: .75rem; border-radius: 1rem; background: var(--theme-bg-elevated); padding: .6rem; box-shadow: inset 0 0 0 1px var(--theme-border); transition: transform 150ms ease, box-shadow 150ms ease; }
.ai-pick:hover,.ai-pick:focus-visible { transform: translateY(-2px); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-accent-primary) 45%, transparent); }
@media (min-width: 640px) { .ai-insight { padding: 1.5rem; } }
@media (max-width: 480px) { .ai-insight__head > button { width: 100%; } .ai-insight__metrics { gap: .35rem; } .ai-insight__metrics div { padding: .65rem .35rem; } }
@media (prefers-reduced-motion: reduce) {
  .ai-taste-bar__fill { transition: none; }
}
</style>
