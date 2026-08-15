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
const average = ref(0)
const count = ref(0)
const saving = ref(false)
const loaded = ref(false)
const loadError = ref(false)

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
  <div>
    <div class="mb-3 flex items-center gap-2">
      <RatingSourceLogo source="site" />
      <h3 class="text-sm font-black text-ink">امتیاز کاربران سایت</h3>
    </div>
    <div class="flex items-center gap-2">
      <CinematicIcon name="star" class="size-5 text-primary-500" filled />
      <template v-if="loaded && count > 0 && average > 0">
        <span class="ltr-value text-xl font-black text-ink" dir="ltr">{{ average.toFixed(1) }}</span>
        <span class="text-xs text-muted">از ۱۰</span>
        <span class="text-[11px] text-muted">از {{ count.toLocaleString('fa-IR') }} رأی</span>
      </template>
      <template v-else-if="loadError">
        <span class="text-sm text-muted">اطلاعات موجود نیست</span>
      </template>
      <template v-else>
        <span class="text-sm text-muted">هنوز امتیازی ثبت نشده</span>
      </template>
    </div>
    <p class="mb-2 mt-4 text-sm font-black text-secondary">امتیاز شما</p>
    <div class="flex flex-wrap gap-1.5" role="group" aria-label="ثبت امتیاز کاربران سایت">
      <button
        v-for="score in 10"
        :key="score"
        type="button"
        class="grid size-11 place-items-center rounded-xl text-xs font-black transition disabled:opacity-60"
        :disabled="saving"
        :aria-pressed="score === selected"
        :class="score <= selected
          ? 'bg-primary-500 text-night-950'
          : dark
            ? 'bg-white/5 text-muted ring-1 ring-white/10 hover:bg-white/10 hover:text-ink'
            : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'"
        @click="selectRating(score)"
      >
        {{ score }}
      </button>
    </div>
    <p class="mt-3 text-[11px] leading-5" :class="dark ? 'text-slate-500' : 'text-slate-400'">
      {{ authStore.isAuthenticated ? 'امتیاز تو روی حساب کاربری‌ات ذخیره می‌شود.' : 'برای ثبت امتیاز وارد حساب شو.' }}
    </p>
  </div>
</template>
