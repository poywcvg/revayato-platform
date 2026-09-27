<script setup lang="ts">
import type { PublicProfileReview } from '~/types'

const props = defineProps<{ review: PublicProfileReview }>()

const revealed = ref(false)
const showSpoiler = computed(() => props.review.is_spoiler && !revealed.value)
const to = computed(() => (props.review.content ? titlePath(props.review.content.content_type, props.review.content.slug) : ''))
const year = computed(() => {
  const c = props.review.content
  if (!c) return ''
  const y = contentYear(c)
  return y ? y.toLocaleString('fa-IR', { useGrouping: false }) : ''
})
const scoreLabel = computed(() => props.review.score.toLocaleString('fa-IR', { minimumFractionDigits: 0, maximumFractionDigits: 1 }))
</script>

<template>
  <article class="review-card">
    <NuxtLink v-if="to" :to="to" class="review-card__poster">
      <CinematicImage :src="review.content?.poster" :alt="review.content?.title || ''" ratio="poster" />
    </NuxtLink>
    <div class="min-w-0 flex-1">
      <div class="flex items-start justify-between gap-2">
        <component :is="to ? 'NuxtLink' : 'span'" :to="to || undefined" class="review-card__title">
          {{ review.content?.title || 'عنوان حذف‌شده' }}
          <span v-if="year" class="review-card__year font-latin" dir="ltr">{{ year }}</span>
        </component>
        <span class="review-card__score"><CinematicIcon name="star" class="size-3.5" filled />{{ scoreLabel }}</span>
      </div>

      <p v-if="review.review" class="review-card__text" :class="showSpoiler && 'review-card__text--masked'">
        {{ review.review }}
      </p>
      <button v-if="showSpoiler" type="button" class="review-card__reveal" @click="revealed = true">
        <CinematicIcon name="eye" class="size-3.5" />نمایش نقد (اسپویلر)
      </button>
    </div>
  </article>
</template>

<style scoped>
.review-card {
  display: flex;
  gap: 0.85rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 72%, transparent);
  border-radius: 1.1rem;
  background: var(--theme-bg-surface);
  padding: 0.85rem;
}
.review-card__poster { width: 3.75rem; flex: none; overflow: hidden; border-radius: 0.7rem; }
.review-card__title {
  display: block;
  color: var(--theme-text-primary);
  font-size: 0.86rem;
  font-weight: 900;
  line-height: 1.4;
}
a.review-card__title:hover { color: var(--theme-accent-primary); }
.review-card__year { margin-inline-start: 0.35rem; color: var(--theme-text-muted); font-size: 0.75rem; font-weight: 700; }
.review-card__score {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 0.2rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-accent-yellow, #ffc24b) 16%, transparent);
  padding: 0.15rem 0.5rem;
  color: var(--theme-accent-yellow, #ffc24b);
  font-size: 0.72rem;
  font-weight: 900;
}
.review-card__text {
  margin-top: 0.5rem;
  color: var(--theme-text-secondary);
  font-size: 0.78rem;
  line-height: 1.75;
  overflow-wrap: anywhere;
}
.review-card__text--masked { filter: blur(6px); user-select: none; }
.review-card__reveal {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-top: 0.5rem;
  color: var(--theme-accent-primary);
  font-size: 0.72rem;
  font-weight: 800;
}
</style>
