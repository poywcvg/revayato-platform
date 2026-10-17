<script setup lang="ts">
import type { CollectionItem, UserCollection } from '~/types'

const props = defineProps<{ collection: UserCollection; canManage?: boolean }>()
const emit = defineEmits<{ edit: []; remove: [CollectionItem] }>()

const notifications = useNotifications()
const config = useRuntimeConfig()

const siteBase = computed(() => {
  const configured = String(config.public.siteUrl || '').replace(/\/$/, '')
  if (configured) return configured
  if (import.meta.client) return window.location.origin
  return 'https://revayato.com'
})
const shareLink = computed(() => `${siteBase.value}${props.collection.share_url}`)
const items = computed(() => props.collection.items ?? [])
const isEmpty = computed(() => items.value.length === 0)

async function shareCollection() {
  if (!import.meta.client) return
  const payload = { title: props.collection.title, url: shareLink.value, text: props.collection.description || props.collection.title }
  try {
    if (navigator.share) {
      await navigator.share(payload)
      return
    }
    await navigator.clipboard.writeText(shareLink.value)
    notifications.success('لینک کالکشن کپی شد', 'حالا می‌توانی آن را برای دوستانت بفرستی.')
  } catch {
    /* user cancelled */
  }
}

async function copyLink() {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(shareLink.value)
    notifications.success('لینک کپی شد', shareLink.value)
  } catch {
    notifications.error('کپی نشد', 'لینک را دستی انتخاب کن.')
  }
}

function year(item: CollectionItem) {
  const y = contentYear(item)
  return y ? y.toLocaleString('fa-IR', { useGrouping: false }) : ''
}
</script>

<template>
  <div class="cdetail" :style="{ '--coll-accent': collection.accent }">
    <header class="cdetail__hero">
      <CollectionCoverCollage :covers="collection.covers" :accent="collection.accent" rounded="0" class="cdetail__cover" />
      <div class="cdetail__scrim" aria-hidden="true" />
      <div class="cdetail__head">
        <div class="cdetail__badges">
          <CollectionVisibilityBadge :visibility="collection.visibility" solid />
          <span class="cdetail__count">{{ collection.item_count.toLocaleString('fa-IR') }} عنوان</span>
        </div>
        <h1 class="cdetail__title">{{ collection.title }}</h1>
        <NuxtLink :to="`/u/${collection.owner.username}`" class="cdetail__owner">
          <span class="cdetail__avatar">
            <img v-if="collection.owner.avatar" :src="collection.owner.avatar" alt="" class="size-full object-cover">
            <span v-else>{{ collection.owner.username.charAt(0).toUpperCase() }}</span>
          </span>
          <span class="font-latin" dir="ltr">@{{ collection.owner.username }}</span>
        </NuxtLink>
      </div>
    </header>

    <p v-if="collection.description" class="cdetail__desc">{{ collection.description }}</p>

    <div class="cdetail__actions">
      <button type="button" class="ui-primary-button min-h-11" @click="shareCollection">
        <CinematicIcon name="share" class="size-4.5" />اشتراک‌گذاری
      </button>
      <button type="button" class="ui-secondary-button min-h-11" @click="copyLink">
        <CinematicIcon name="document" class="size-4.5" />کپی لینک
      </button>
      <button v-if="canManage" type="button" class="ui-ghost-button min-h-11" @click="emit('edit')">
        <CinematicIcon name="edit" class="size-4.5" />ویرایش
      </button>
    </div>

    <EmptyState
      v-if="isEmpty"
      title="این کالکشن هنوز خالی است"
      :description="canManage ? 'از صفحهٔ هر فیلم یا سریال، دکمهٔ «کالکشن» را بزن تا اینجا اضافه شود.' : 'صاحب این کالکشن هنوز عنوانی به آن اضافه نکرده است.'"
      icon="layers"
      :action-label="canManage ? 'مرور فیلم‌ها' : ''"
      :action-href="canManage ? '/movies' : ''"
    />

    <ul v-else class="cdetail__grid">
      <li v-for="item in items" :key="`${item.content_type}-${item.id}`" class="cdetail__cell">
        <NuxtLink :to="titlePath(item.content_type, item.slug)" class="cdetail__poster group">
          <CinematicImage :src="item.poster" :alt="item.title" ratio="poster" image-class="transition duration-300 group-hover:scale-105" />
          <span v-if="item.site_rating" class="cdetail__rating"><CinematicIcon name="star" class="size-3" filled />{{ item.site_rating.toLocaleString('fa-IR') }}</span>
          <button
            v-if="canManage"
            type="button"
            class="cdetail__remove"
            :aria-label="`حذف ${item.title} از کالکشن`"
            @click.prevent="emit('remove', item)"
          >
            <CinematicIcon name="x" class="size-4" />
          </button>
        </NuxtLink>
        <NuxtLink :to="titlePath(item.content_type, item.slug)" class="cdetail__name">{{ item.title }}</NuxtLink>
        <span v-if="year(item)" class="cdetail__year font-latin" dir="ltr">{{ year(item) }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.cdetail { display: flex; flex-direction: column; gap: 1rem; }

.cdetail__hero {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  min-height: 12rem;
  border-radius: 1.5rem;
}

.cdetail__cover { position: absolute; inset: 0; }
.cdetail__scrim {
  position: absolute;
  inset: 0;
  z-index: 2;
  background: linear-gradient(to top, rgb(3 6 5 / 92%), rgb(3 6 5 / 45%) 55%, transparent);
}

.cdetail__head { position: relative; z-index: 3; display: flex; flex-direction: column; gap: 0.5rem; padding: 1.25rem; padding-top: 6rem; }
.cdetail__badges { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.cdetail__count {
  border-radius: 999px;
  background: color-mix(in srgb, var(--coll-accent) 85%, black);
  padding: 0.15rem 0.55rem;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 900;
}
.cdetail__title { color: #fff; font-size: clamp(1.5rem, 6vw, 2.4rem); font-weight: 900; line-height: 1.15; text-wrap: balance; }

.cdetail__owner { display: inline-flex; align-items: center; gap: 0.45rem; width: fit-content; color: rgb(255 255 255 / 82%); font-size: 0.78rem; font-weight: 700; }
.cdetail__owner:hover { color: #fff; }
.cdetail__avatar {
  display: grid; width: 1.6rem; height: 1.6rem; flex: none; place-items: center; overflow: hidden;
  border-radius: 999px; background: linear-gradient(145deg, var(--theme-accent-primary), var(--theme-primary-700));
  color: var(--theme-on-accent); font-size: 0.75rem; font-weight: 900;
}

.cdetail__desc { max-width: 46rem; color: var(--theme-text-secondary); font-size: 0.85rem; line-height: 1.85; }

.cdetail__actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.cdetail__actions > * { flex: 1 1 auto; }
@media (min-width: 640px) { .cdetail__actions > * { flex: 0 0 auto; } }

.cdetail__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}
@media (min-width: 640px) { .cdetail__grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; } }
@media (min-width: 1024px) { .cdetail__grid { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
@media (min-width: 1536px) { .cdetail__grid { grid-template-columns: repeat(var(--rail-columns), minmax(0, 1fr)); } }

.cdetail__cell { min-width: 0; }
.cdetail__poster {
  position: relative;
  display: block;
  overflow: hidden;
  border-radius: 0.9rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 70%, transparent);
}
.cdetail__rating {
  position: absolute;
  inset: auto auto 0.4rem 0.4rem;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  border-radius: 999px;
  background: rgb(5 8 7 / 78%);
  padding: 0.1rem 0.4rem;
  color: var(--theme-accent-yellow, #ffc24b);
  font-size: 0.75rem;
  font-weight: 900;
}
.cdetail__remove {
  position: absolute;
  inset: 0.4rem 0.4rem auto auto;
  z-index: 2;
  display: grid;
  width: 1.75rem;
  height: 1.75rem;
  place-items: center;
  border-radius: 999px;
  background: rgb(5 8 7 / 72%);
  color: #fff;
  opacity: 0;
  transition: opacity 150ms ease, background-color 150ms ease;
}
.cdetail__poster:hover .cdetail__remove,
.cdetail__remove:focus-visible { opacity: 1; }
.cdetail__remove:hover { background: var(--theme-error, #ef4444); }
@media (hover: none) { .cdetail__remove { opacity: 1; } }

.cdetail__name {
  display: block;
  margin-top: 0.4rem;
  overflow: hidden;
  color: var(--theme-text-primary);
  font-size: 0.76rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cdetail__name:hover { color: var(--theme-accent-primary); }
.cdetail__year { display: block; color: var(--theme-text-muted); font-size: 0.75rem; }
</style>
