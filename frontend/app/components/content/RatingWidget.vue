<script setup lang="ts">
import type { ContentType, RatingSummary } from '~/types'

const props = withDefaults(defineProps<{
  objectId: number
  slug?: string
  contentType?: ContentType
  initialRating?: number
  dark?: boolean
}>(), {
  slug: '',
  contentType: 'movie',
  initialRating: 0,
  dark: false,
})

const { api } = useApi()
const authStore = useAuthStore()
const route = useRoute()
const { trackRatingAction } = useAnalyticsEvent()
const notifications = useNotifications()

const selected = ref(0)
const hovered = ref(0)
const average = ref(0)
const count = ref(0)
const saving = ref(false)
const loaded = ref(false)
const loadError = ref(false)
const justSaved = ref(false)

// Descriptive word per score — turns an abstract number into an emotional choice
// (labeling effect), which nudges people to commit to a rating.
const SCORE_WORDS: Record<number, string> = {
  1: 'افتضاح',
  2: 'خیلی بد',
  3: 'بد',
  4: 'ضعیف',
  5: 'متوسط',
  6: 'قابل قبول',
  7: 'خوب',
  8: 'خیلی خوب',
  9: 'عالی',
  10: 'شاهکار',
}

// The value the bar/preview currently reflects: what the pointer is over, else
// what the user already picked.
const preview = computed(() => hovered.value || selected.value)
const previewWord = computed(() => (preview.value ? SCORE_WORDS[preview.value] : ''))
const hasVotes = computed(() => loaded.value && count.value > 0 && average.value > 0)
const votesLabel = computed(() => count.value.toLocaleString('fa-IR'))

async function loadSummary() {
  loadError.value = false
  try {
    const summary = await api<RatingSummary>('/engagement/ratings/summary/', {
      query: { content_type: props.contentType, object_id: props.objectId },
    })
    // Only show averages confirmed by the engagement API — never invent scores.
    average.value = summary.average != null && summary.count > 0 ? Number(summary.average) : 0
    count.value = summary.count || 0
    selected.value = summary.my_rating ? Number(summary.my_rating.score) : 0
    loaded.value = true
  } catch {
    loadError.value = true
    average.value = 0
    count.value = 0
  }
}

async function selectRating(score: number) {
  if (!authStore.isAuthenticated) {
    await navigateTo({ path: '/auth/login', query: { redirect: route.fullPath } })
    return
  }
  if (saving.value) return
  if (score < 1 || score > 10) return
  const previous = selected.value
  selected.value = score
  saving.value = true
  try {
    await api('/engagement/ratings/', {
      method: 'POST',
      body: {
        content_type: props.contentType,
        object_id: props.objectId,
        score,
      },
    })
    notifications.success('امتیاز ثبت شد', `امتیاز ${score} از ۱۰ ذخیره شد.`)
    if (props.slug) trackRatingAction({ id: props.objectId, slug: props.slug, type: props.contentType }, score)
    // Micro-reward: flash a confirmation state so the action feels rewarding.
    justSaved.value = true
    setTimeout(() => { justSaved.value = false }, 2200)
    // Refresh from backend before updating visible average.
    await loadSummary()
  } catch (cause) {
    selected.value = previous
    notifications.notifyError(cause, 'امتیاز ثبت نشد.')
  } finally {
    saving.value = false
  }
}

onMounted(() => { void loadSummary() })
watch(() => [props.objectId, props.contentType], () => { void loadSummary() })
</script>

<template>
  <section class="rw" :class="{ 'rw--dark': dark, 'rw--nudge': loaded && !selected }" aria-labelledby="rw-title">
    <!-- Header: identity + live social proof -->
    <header class="rw__head">
      <div class="rw__head-l">
        <RatingSourceLogo source="site" />
        <h3 id="rw-title" class="rw__title">امتیاز کاربران</h3>
      </div>
      <span v-if="hasVotes" class="rw__badge">
        <CinematicIcon name="user" class="size-3" />
        {{ votesLabel }} رأی
      </span>
    </header>

    <!-- Anchor: the community average (or a pioneer invite when empty) -->
    <div class="rw__score">
      <template v-if="hasVotes">
        <div class="rw__avg">
          <CinematicIcon name="star" class="rw__avg-star" filled />
          <span class="rw__avg-num ltr-value" dir="ltr">{{ average.toFixed(1) }}</span>
          <span class="rw__avg-max">/ ۱۰</span>
        </div>
        <p class="rw__avg-sub">میانگین امتیاز {{ votesLabel }} کاربر</p>
      </template>
      <template v-else-if="loadError">
        <p class="rw__empty">امتیازها در دسترس نیست.</p>
      </template>
      <template v-else>
        <div class="rw__pioneer">
          <CinematicIcon name="star" class="rw__pioneer-star" filled />
          <div>
            <p class="rw__pioneer-title">هنوز کسی امتیاز نداده!</p>
            <p class="rw__pioneer-sub">اولین نفری باش که نظرش را ثبت می‌کند.</p>
          </div>
        </div>
      </template>
    </div>

    <!-- The ask: prominent, low-friction 1–10 rating bar -->
    <div class="rw__ask">
      <div class="rw__ask-row">
        <span class="rw__ask-label">
          {{ selected ? 'امتیاز تو' : 'نظر تو چیه؟' }}
        </span>
        <transition name="rw-pop">
          <span v-if="preview" :key="preview" class="rw__preview" dir="ltr">
            <b class="ltr-value">{{ preview }}</b>
            <span class="rw__preview-word">{{ previewWord }}</span>
          </span>
        </transition>
      </div>

      <div
        class="rw__bar"
        role="group"
        aria-label="ثبت امتیاز شما از ۱ تا ۱۰"
        @mouseleave="hovered = 0"
      >
        <button
          v-for="score in 10"
          :key="score"
          type="button"
          class="rw__seg"
          :class="{ 'rw__seg--on': score <= preview, 'rw__seg--mine': selected && score <= selected && !hovered }"
          :disabled="saving"
          :aria-pressed="score === selected"
          :aria-label="`${score} از ۱۰`"
          @mouseenter="hovered = score"
          @focus="hovered = score"
          @blur="hovered = 0"
          @click="selectRating(score)"
        >
          <span class="rw__seg-num ltr-value">{{ score }}</span>
        </button>
      </div>

      <transition name="rw-fade" mode="out-in">
        <p v-if="justSaved" key="saved" class="rw__hint rw__hint--ok">
          <CinematicIcon name="check" class="size-3.5" />
          ثبت شد! ممنون که نظرت را گفتی.
        </p>
        <p v-else-if="selected" key="mine" class="rw__hint">
          امتیاز تو <b class="ltr-value" dir="ltr">{{ selected }}</b> از ۱۰ است — برای تغییر، عدد دیگری بزن.
        </p>
        <p v-else-if="authStore.isAuthenticated" key="cta" class="rw__hint">
          یک ضربه کافیست تا نظرت روی رتبه‌بندی سایت اثر بگذارد.
        </p>
        <p v-else key="login" class="rw__hint">
          برای ثبت امتیاز وارد حساب شو.
        </p>
      </transition>
    </div>
  </section>
</template>

<style scoped>
.rw {
  position: relative;
  border-radius: 1.25rem;
  padding: 1.15rem 1.15rem 1.25rem;
  background:
    radial-gradient(120% 140% at 100% 0%, rgb(var(--media-accent-rgb, 176 228 204) / 14%), transparent 55%),
    var(--surface-1, #fff);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
  box-shadow: none;
  overflow: hidden;
}
.rw--dark {
  background:
    radial-gradient(120% 140% at 100% 0%, rgb(var(--media-accent-rgb, 176 228 204) / 18%), transparent 55%),
    rgb(255 255 255 / 3%);
  border-color: rgb(255 255 255 / 10%);
}
/* Zeigarnik nudge: a soft accent glow while the viewer hasn't rated yet. */
.rw--nudge {
  border-color: rgb(var(--media-accent-rgb, 176 228 204) / 45%);
  box-shadow: 0 0 0 1px rgb(var(--media-accent-rgb, 176 228 204) / 22%);
}

.rw__head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.rw__head-l { display: flex; align-items: center; gap: 0.5rem; }
.rw__title { font-size: 0.9rem; font-weight: 900; color: var(--text-primary, #0b0b0f); }
.rw__badge {
  display: inline-flex; align-items: center; gap: 0.3rem;
  padding: 0.2rem 0.55rem; border-radius: 999px;
  font-size: 0.75rem; font-weight: 800;
  color: var(--media-accent, #0a7d55);
  background: rgb(var(--media-accent-rgb, 176 228 204) / 14%);
}

.rw__score { margin-top: 0.85rem; min-height: 2.75rem; }
.rw__avg { display: flex; align-items: baseline; gap: 0.35rem; }
.rw__avg-star { width: 1.6rem; height: 1.6rem; color: #f5c518; align-self: center; }
.rw__avg-num { font-size: 2.1rem; line-height: 1; font-weight: 900; color: var(--text-primary, #0b0b0f); }
.rw__avg-max { font-size: 0.8rem; font-weight: 800; color: var(--text-muted, #6b7280); }
.rw__avg-sub { margin-top: 0.3rem; font-size: 0.75rem; color: var(--text-muted, #6b7280); }
.rw__empty { font-size: 0.85rem; color: var(--text-muted, #6b7280); }

.rw__pioneer { display: flex; align-items: center; gap: 0.6rem; }
.rw__pioneer-star { width: 1.7rem; height: 1.7rem; color: var(--media-accent, #0a7d55); }
.rw__pioneer-title { font-size: 0.9rem; font-weight: 900; color: var(--text-primary, #0b0b0f); }
.rw__pioneer-sub { font-size: 0.72rem; color: var(--text-muted, #6b7280); margin-top: 0.1rem; }

.rw__ask { margin-top: 1rem; }
.rw__ask-row { display: flex; align-items: center; justify-content: space-between; min-height: 1.5rem; }
.rw__ask-label { font-size: 0.8rem; font-weight: 900; color: var(--text-secondary, #374151); }
.rw__preview { display: inline-flex; align-items: center; gap: 0.4rem; }
.rw__preview b { font-size: 1.05rem; font-weight: 900; color: var(--media-accent, #0a7d55); }
.rw__preview-word {
  font-size: 0.75rem; font-weight: 800; color: var(--media-accent, #0a7d55);
  padding: 0.12rem 0.45rem; border-radius: 999px;
  background: rgb(var(--media-accent-rgb, 176 228 204) / 16%);
}

.rw__bar {
  margin-top: 0.55rem;
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 0.28rem;
}
.rw__seg {
  position: relative;
  height: 2.6rem;
  border-radius: 0.6rem;
  display: grid; place-items: center;
  font-weight: 900;
  cursor: pointer;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
  background: var(--surface-2, rgba(0, 0, 0, 0.03));
  color: var(--text-muted, #9ca3af);
  transition: transform 0.12s ease, background 0.12s ease, color 0.12s ease, box-shadow 0.12s ease;
}
.rw--dark .rw__seg { background: rgb(255 255 255 / 5%); border-color: rgb(255 255 255 / 10%); }
.rw__seg-num { font-size: 0.78rem; }
.rw__seg:hover:not(:disabled) { transform: translateY(-2px); }
.rw__seg:disabled { opacity: 0.6; cursor: default; }
/* Goal-gradient fill: everything up to the pointer lights up in the accent. */
.rw__seg--on {
  background: var(--media-accent, #0a7d55);
  border-color: transparent;
  color: #fff;
  box-shadow: none;
}
.rw--dark .rw__seg--on { color: #05130d; }
/* The already-saved rating stays visible with a subtly different tone. */
.rw__seg--mine {
  background: rgb(var(--media-accent-rgb, 176 228 204) / 40%);
  color: var(--text-primary, #0b0b0f);
}

.rw__hint { margin-top: 0.7rem; font-size: 0.75rem; line-height: 1.5; color: var(--text-muted, #6b7280); }
.rw__hint b { color: var(--media-accent, #0a7d55); }
.rw__hint--ok {
  display: inline-flex; align-items: center; gap: 0.3rem;
  font-weight: 800; color: var(--accent-success, #10b981);
}

.rw-pop-enter-active { transition: transform 0.14s ease, opacity 0.14s ease; }
.rw-pop-enter-from { transform: translateY(3px) scale(0.9); opacity: 0; }
.rw-fade-enter-active, .rw-fade-leave-active { transition: opacity 0.18s ease; }
.rw-fade-enter-from, .rw-fade-leave-to { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .rw__seg, .rw-pop-enter-active, .rw-fade-enter-active, .rw-fade-leave-active { transition: none; }
}
</style>
