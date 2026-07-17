<script setup lang="ts">
import type { ContentType } from '~/types'

const props = withDefaults(defineProps<{ objectId: number; slug?: string; contentType?: ContentType; initialRating?: number; dark?: boolean }>(), { slug: '', contentType: 'movie', initialRating: 0, dark: false })
const selected = useState<number>(`mock-rating-${props.objectId}`, () => 0)
const { trackRatingAction } = useAnalyticsEvent()
const notifications = useNotifications()

function selectRating(score: number) {
  selected.value = score
  notifications.success('امتیاز ثبت شد', `امتیاز ${score} از ۱۰ برای پیشنهادهای بعدی ذخیره شد.`)
  if (props.slug) trackRatingAction({ id: props.objectId, slug: props.slug, type: props.contentType }, score)
}
</script>

<template>
  <div>
    <div class="flex items-center gap-2"><CinematicIcon name="star" class="size-5 text-primary-500" filled /><span class="text-xl font-black text-ink">{{ initialRating?.toFixed(1) || '—' }}</span><span class="text-xs text-muted">از ۱۰</span></div>
    <p class="mb-2 mt-4 text-sm font-black text-secondary">امتیاز شما</p>
    <div class="flex flex-wrap gap-1.5" role="group" aria-label="ثبت امتیاز">
      <button v-for="score in 10" :key="score" type="button" class="grid size-10 place-items-center rounded-xl text-xs font-black transition" :class="score <= selected ? 'bg-primary-500 text-night-950' : dark ? 'bg-white/5 text-muted ring-1 ring-white/10 hover:bg-white/10 hover:text-ink' : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'" @click="selectRating(score)">{{ score }}</button>
    </div>
    <p class="mt-3 text-[11px] leading-5" :class="dark ? 'text-slate-500' : 'text-slate-400'">در نسخه فعلی، امتیاز تو فقط روی همین دستگاه ذخیره می‌شود.</p>
  </div>
</template>
