<script setup lang="ts">
import type { PublicProfile } from '~/types'

const route = useRoute()
const username = computed(() => String(route.params.username || ''))
const { fetchPublicProfile } = useCollections()
const notifications = useNotifications()
const config = useRuntimeConfig()

const { data: profile, error } = await useAsyncData<PublicProfile>(
  () => `public-profile-${username.value}`,
  () => fetchPublicProfile(username.value),
)

if (error.value) {
  throw createError({ statusCode: 404, statusMessage: 'کاربر پیدا نشد.', fatal: true })
}

const avatarInitial = computed(() => (profile.value?.display_name || profile.value?.username || 'ر').trim().charAt(0).toUpperCase())
const memberYear = computed(() => {
  const raw = profile.value?.member_since
  if (!raw) return ''
  try {
    return new Intl.DateTimeFormat('fa-IR', { year: 'numeric', month: 'long' }).format(new Date(raw))
  } catch {
    return ''
  }
})

const statTiles = computed(() => {
  const s = profile.value?.stats
  if (!s) return []
  return [
    { label: 'کالکشن', value: s.collections },
    { label: 'عنوان', value: s.public_titles },
    { label: 'امتیاز', value: s.ratings },
  ]
})

const siteBase = computed(() => {
  const configured = String(config.public.siteUrl || '').replace(/\/$/, '')
  if (configured) return configured
  if (import.meta.client) return window.location.origin
  return 'https://revayato.com'
})

async function shareProfile() {
  if (!import.meta.client || !profile.value) return
  const url = `${siteBase.value}/u/${profile.value.username}`
  try {
    if (navigator.share) {
      await navigator.share({ title: `پروفایل ${profile.value.username}`, url })
      return
    }
    await navigator.clipboard.writeText(url)
    notifications.success('لینک پروفایل کپی شد', url)
  } catch {
    /* cancelled */
  }
}

useSeoMeta({
  title: () => (profile.value ? `${profile.value.display_name || profile.value.username} — روایتو` : 'پروفایل'),
  description: () => profile.value?.bio || `پروفایل عمومی ${username.value} در روایتو`,
})
</script>

<template>
  <div v-if="profile" class="cinema-page page-section pb-14 sm:pb-20">
    <header class="pub-hero">
      <span class="pub-hero__glow" aria-hidden="true" />
      <div class="pub-hero__identity">
        <span class="pub-avatar">
          <img v-if="profile.avatar" :src="profile.avatar" alt="" class="size-full object-cover">
          <span v-else>{{ avatarInitial }}</span>
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="pub-name font-latin" dir="ltr">{{ profile.display_name || profile.username }}</h1>
            <span v-if="profile.is_verified" class="pub-verified"><CinematicIcon name="shield-check" class="size-3.5" />تأییدشده</span>
          </div>
          <p class="pub-handle font-latin" dir="ltr">@{{ profile.username }}</p>
          <p v-if="profile.bio" class="pub-bio">{{ profile.bio }}</p>
          <p v-if="memberYear" class="pub-member"><CinematicIcon name="calendar" class="size-3.5" />عضو روایتو از {{ memberYear }}</p>
        </div>
      </div>

      <div class="pub-hero__actions">
        <button type="button" class="ui-secondary-button min-h-11" @click="shareProfile">
          <CinematicIcon name="share" class="size-4.5" />اشتراک پروفایل
        </button>
        <NuxtLink v-if="profile.is_self" to="/profile" class="ui-ghost-button min-h-11">
          <CinematicIcon name="edit" class="size-4.5" />ویرایش پروفایل من
        </NuxtLink>
      </div>
    </header>

    <!-- Private profile: minimal card only. -->
    <EmptyState
      v-if="profile.is_private"
      class="mt-6"
      title="این پروفایل خصوصی است"
      description="این کاربر نمایش عمومی پروفایلش را خاموش کرده است."
      icon="lock"
    />

    <template v-else>
      <div v-if="statTiles.length" class="pub-stats">
        <div v-for="tile in statTiles" :key="tile.label" class="pub-stat">
          <strong>{{ tile.value.toLocaleString('fa-IR') }}</strong>
          <span>{{ tile.label }}</span>
        </div>
      </div>

      <!-- Collections -->
      <section v-if="profile.collections?.length" class="mt-8">
        <div class="mb-3 flex items-center gap-2">
          <CinematicIcon name="layers" class="size-5 text-brand" />
          <h2 class="text-lg font-black text-ink">کالکشن‌ها</h2>
        </div>
        <div class="pub-coll-grid">
          <CollectionSummaryCard
            v-for="collection in profile.collections"
            :key="collection.id"
            :collection="collection"
            :to="collection.share_url"
          />
        </div>
      </section>

      <!-- Reviews -->
      <section v-if="profile.reviews?.length" class="mt-8">
        <div class="mb-3 flex items-center gap-2">
          <CinematicIcon name="comment" class="size-5 text-brand" />
          <h2 class="text-lg font-black text-ink">نقدها</h2>
        </div>
        <div class="pub-reviews">
          <ProfileReviewCard v-for="(review, index) in profile.reviews" :key="index" :review="review" />
        </div>
      </section>

      <EmptyState
        v-if="!profile.collections?.length && !profile.reviews?.length"
        class="mt-6"
        title="هنوز فعالیتی عمومی نیست"
        description="این کاربر هنوز کالکشن عمومی یا نقدی منتشر نکرده است."
        icon="film"
      />
    </template>
  </div>
</template>

<style scoped>
.pub-hero {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 78%, transparent);
  border-radius: 1.5rem;
  background: linear-gradient(145deg, color-mix(in srgb, var(--theme-accent-primary) 8%, var(--theme-bg-surface)), var(--theme-bg-surface) 55%);
  padding: 1.25rem;
}
@media (min-width: 768px) {
  .pub-hero { flex-direction: row; align-items: center; justify-content: space-between; gap: 2rem; padding: 1.75rem; }
}

.pub-hero__glow {
  position: absolute;
  z-index: -1;
  inset: -6rem -4rem auto auto;
  width: 16rem;
  height: 16rem;
  border-radius: 999px;
  background: radial-gradient(circle, color-mix(in srgb, var(--theme-accent-primary) 20%, transparent), transparent 68%);
  pointer-events: none;
}

.pub-hero__identity { display: flex; min-width: 0; align-items: flex-start; gap: 1rem; }

.pub-avatar {
  display: grid;
  width: 4.75rem;
  height: 4.75rem;
  flex: none;
  place-items: center;
  overflow: hidden;
  border: 3px solid color-mix(in srgb, var(--theme-accent-primary) 35%, transparent);
  border-radius: 1.5rem;
  background: linear-gradient(145deg, var(--theme-accent-primary), var(--theme-primary-700));
  color: var(--theme-on-accent);
  font-family: var(--font-latin-ui);
  font-size: 1.6rem;
  font-weight: 900;
}
@media (min-width: 640px) { .pub-avatar { width: 5.5rem; height: 5.5rem; } }

.pub-name { overflow-wrap: anywhere; color: var(--theme-text-primary); font-size: clamp(1.35rem, 6vw, 2rem); font-weight: 900; line-height: 1.15; }
.pub-verified {
  display: inline-flex; align-items: center; gap: 0.25rem;
  border: 1px solid color-mix(in srgb, var(--theme-success) 30%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-success) 9%, transparent);
  padding: 0.2rem 0.5rem;
  color: var(--theme-success);
  font-size: 0.75rem;
  font-weight: 800;
}
.pub-handle { margin-top: 0.15rem; color: var(--theme-accent-primary); font-size: 0.8rem; font-weight: 700; }
.pub-bio { margin-top: 0.5rem; max-width: 42rem; color: var(--theme-text-secondary); font-size: 0.82rem; line-height: 1.8; }
.pub-member { display: flex; align-items: center; gap: 0.35rem; margin-top: 0.5rem; color: var(--theme-text-muted); font-size: 0.75rem; }

.pub-hero__actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }

.pub-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.6rem;
  margin-top: 1.25rem;
  max-width: 30rem;
}
.pub-stat {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 70%, transparent);
  border-radius: 1rem;
  background: var(--theme-bg-surface);
  padding: 0.85rem 0.5rem;
  text-align: center;
}
.pub-stat strong { color: var(--theme-text-primary); font-size: 1.35rem; font-weight: 900; }
.pub-stat span { color: var(--theme-text-muted); font-size: 0.75rem; font-weight: 700; }

.pub-coll-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 15rem), 1fr));
  gap: 1rem;
}
.pub-reviews { display: grid; gap: 0.75rem; }
@media (min-width: 768px) { .pub-reviews { grid-template-columns: 1fr 1fr; } }
</style>
