<script setup lang="ts">
import type { RatingSource } from '~/types/ratings'
import { getRatingSourceConfig } from '~/data/ratingSources'

const props = defineProps<{ source: RatingSource }>()

const config = computed(() => getRatingSourceConfig(props.source))
const failed = ref(false)

watch(() => props.source, () => { failed.value = false })
</script>

<template>
  <span class="rating-source-logo" :class="{ 'rating-source-logo--wordmark': config.wordmark }" :title="config.label">
    <img
      v-if="!failed"
      :src="config.logo"
      :alt="config.label"
      class="rating-source-logo__img"
      loading="lazy"
      decoding="async"
      @error="failed = true"
    >
    <span v-else class="rating-source-logo__fallback">{{ config.label }}</span>
  </span>
</template>

<style scoped>
.rating-source-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  min-inline-size: 1.5rem;
  max-inline-size: 4.5rem;
  block-size: 1.5rem;
}

.rating-source-logo--wordmark {
  max-inline-size: 5rem;
}

.rating-source-logo__img {
  inline-size: auto;
  block-size: 24px;
  max-inline-size: 72px;
  object-fit: contain;
}

.rating-source-logo--wordmark .rating-source-logo__img {
  max-inline-size: 80px;
}

.rating-source-logo__fallback {
  font-size: .625rem;
  font-weight: 900;
  letter-spacing: .02em;
  color: var(--text-secondary, var(--theme-text-secondary));
  white-space: nowrap;
}
</style>
