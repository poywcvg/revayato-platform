<script setup lang="ts">
import type { MediaRating } from '~/types/ratings'
import { getRatingSourceConfig } from '~/data/ratingSources'
import { criticTypeLabel, formatScaleLabel, formatVoteCount } from '~/utils/mediaRatings'

const props = defineProps<{ rating: MediaRating }>()

const config = computed(() => getRatingSourceConfig(props.rating.source))
const votes = computed(() => formatVoteCount(props.rating.voteCount))
const scaleLabel = computed(() => formatScaleLabel(props.rating))
const criticLabel = computed(() => criticTypeLabel(props.rating))
const ariaLabel = computed(() => {
  const parts = [
    `امتیاز ${config.value.label}`,
    props.rating.displayValue,
    scaleLabel.value.replace('/', 'از').trim(),
    criticLabel.value,
  ].filter(Boolean)
  return parts.join(' ')
})
const sourceLinkLabel = computed(() => `مشاهده امتیاز این عنوان در ${config.value.label}`)
</script>

<template>
  <component
    :is="rating.url ? 'a' : 'div'"
    class="media-rating-card"
    :href="rating.url || undefined"
    :target="rating.url ? '_blank' : undefined"
    :rel="rating.url ? 'noopener noreferrer' : undefined"
    :aria-label="rating.url ? sourceLinkLabel : ariaLabel"
  >
    <div class="media-rating-card__top">
      <RatingSourceLogo :source="rating.source" />
      <div class="media-rating-card__score ltr-value" dir="ltr">
        <span class="media-rating-card__value">{{ rating.displayValue }}</span>
        <span v-if="scaleLabel" class="media-rating-card__scale">{{ scaleLabel }}</span>
      </div>
    </div>
    <p v-if="criticLabel || votes" class="media-rating-card__meta">
      <span v-if="criticLabel">{{ criticLabel }}</span>
      <span v-if="criticLabel && votes" aria-hidden="true"> · </span>
      <span v-if="votes">{{ votes }}</span>
    </p>
    <p
      v-if="rating.updatedAt"
      class="media-rating-card__updated"
      :title="`به‌روزرسانی: ${new Date(rating.updatedAt).toLocaleString('fa-IR')}`"
    >
      <span class="sr-only">آخرین به‌روزرسانی</span>
    </p>
  </component>
</template>

<style scoped>
.media-rating-card {
  display: flex;
  min-height: 4.25rem;
  flex-direction: column;
  justify-content: center;
  gap: .35rem;
  border-radius: var(--radius-md, 12px);
  padding: .75rem .85rem;
  background: var(--surface-2, var(--theme-bg-elevated));
  box-shadow: inset 0 0 0 1px var(--border-subtle, var(--theme-border));
  color: inherit;
  text-decoration: none;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    transform 160ms ease;
}

a.media-rating-card:hover {
  background: var(--surface-3, var(--theme-bg-elevated));
  transform: translateY(-1px);
}

.media-rating-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
}

.media-rating-card__score {
  display: inline-flex;
  align-items: baseline;
  gap: .3rem;
  font-variant-numeric: tabular-nums;
}

.media-rating-card__value {
  font-size: 1.05rem;
  font-weight: 900;
  color: var(--text-primary, var(--theme-text-primary));
}

.media-rating-card__scale {
  font-size: .7rem;
  font-weight: 700;
  color: var(--text-muted, var(--theme-text-muted));
}

.media-rating-card__meta {
  margin: 0;
  font-size: .68rem;
  font-weight: 700;
  color: var(--text-secondary, var(--theme-text-secondary));
}

.media-rating-card__updated {
  margin: 0;
  height: 0;
  overflow: hidden;
}
</style>
