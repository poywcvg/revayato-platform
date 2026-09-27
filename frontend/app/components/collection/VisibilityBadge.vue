<script setup lang="ts">
import type { CollectionVisibility } from '~/types'

const props = defineProps<{ visibility: CollectionVisibility; solid?: boolean }>()
const meta = computed(() => COLLECTION_VISIBILITY[props.visibility] ?? COLLECTION_VISIBILITY.public)
</script>

<template>
  <span class="vis-badge" :class="solid && 'vis-badge--solid'">
    <CinematicIcon :name="meta.icon" class="size-3" />
    {{ meta.label }}
  </span>
</template>

<style scoped>
.vis-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border-radius: 999px;
  padding: 0.15rem 0.5rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 78%, transparent);
  color: var(--theme-text-secondary);
  font-size: 0.75rem;
  font-weight: 800;
  line-height: 1.4;
  white-space: nowrap;
}

.vis-badge--solid {
  background: rgb(5 8 7 / 62%);
  color: #fff;
  backdrop-filter: blur(6px);
}
</style>
