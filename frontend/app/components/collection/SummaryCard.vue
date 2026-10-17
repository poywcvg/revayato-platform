<script setup lang="ts">
import type { UserCollection } from '~/types'

const props = defineProps<{ collection: UserCollection; to: string }>()

const countLabel = computed(() => `${props.collection.item_count.toLocaleString('fa-IR')} عنوان`)
</script>

<template>
  <NuxtLink :to="to" class="coll-card group" :style="{ '--coll-accent': collection.accent }">
    <div class="coll-card__cover">
      <CollectionCoverCollage :covers="collection.covers" :accent="collection.accent" rounded="0">
        <div class="coll-card__overlay">
          <CollectionVisibilityBadge :visibility="collection.visibility" solid />
          <span class="coll-card__count">{{ countLabel }}</span>
        </div>
      </CollectionCoverCollage>
    </div>
    <div class="coll-card__body">
      <h3 class="coll-card__title">{{ collection.title }}</h3>
      <p v-if="collection.description" class="coll-card__desc">{{ collection.description }}</p>
      <div class="coll-card__owner">
        <span class="coll-card__avatar">
          <img v-if="collection.owner.avatar" :src="collection.owner.avatar" alt="" class="size-full object-cover">
          <span v-else>{{ collection.owner.username.charAt(0).toUpperCase() }}</span>
        </span>
        <span class="font-latin" dir="ltr">@{{ collection.owner.username }}</span>
      </div>
    </div>
  </NuxtLink>
</template>

<style scoped>
.coll-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--theme-border) 78%, transparent);
  border-radius: 1.1rem;
  background: var(--theme-bg-surface);
  transition: border-color 180ms ease, transform 180ms ease, box-shadow 180ms ease;
}

.coll-card:hover,
.coll-card:focus-visible {
  border-color: color-mix(in srgb, var(--coll-accent, var(--theme-accent-primary)) 55%, transparent);
  transform: translateY(-2px);
  box-shadow: none;
}

.coll-card__cover {
  position: relative;
  aspect-ratio: 16 / 10;
}

.coll-card__overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.6rem;
  background: linear-gradient(to top, rgb(0 0 0 / 55%), transparent 70%);
}

.coll-card__count {
  border-radius: 999px;
  background: rgb(5 8 7 / 62%);
  padding: 0.15rem 0.5rem;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 800;
}

.coll-card__body { padding: 0.75rem 0.85rem 0.85rem; }

.coll-card__title {
  overflow: hidden;
  color: var(--theme-text-primary);
  font-size: 0.92rem;
  font-weight: 900;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coll-card__desc {
  display: -webkit-box;
  overflow: hidden;
  margin-top: 0.25rem;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  color: var(--theme-text-muted);
  font-size: 0.75rem;
  line-height: 1.6;
}

.coll-card__owner {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.6rem;
  color: var(--theme-text-muted);
  font-size: 0.75rem;
}

.coll-card__avatar {
  display: grid;
  width: 1.35rem;
  height: 1.35rem;
  flex: none;
  place-items: center;
  overflow: hidden;
  border-radius: 999px;
  background: linear-gradient(145deg, var(--theme-accent-primary), var(--theme-primary-700));
  color: var(--theme-on-accent);
  font-size: 0.75rem;
  font-weight: 900;
}
</style>
