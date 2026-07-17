<script setup lang="ts">
import type { ContentType } from '~/types'

const props = withDefaults(defineProps<{ id: number; slug?: string; contentType?: ContentType; dark?: boolean; iconOnly?: boolean; compactOnMobile?: boolean }>(), { slug: '', contentType: 'movie', dark: false, iconOnly: false, compactOnMobile: false })
const { isInWatchlist, toggleWatchlist } = useLibrary()
const { trackWatchlistAction } = useAnalyticsEvent()
const notifications = useNotifications()
const saved = computed(() => isInWatchlist(props.id))

function handleToggle() {
  const added = !saved.value
  toggleWatchlist(props.id)
  if (added) notifications.success('به «لیست من» اضافه شد', 'هر وقت خواستی از بخش «لیست من» پیدایش می‌کنی.')
  else notifications.info('از «لیست من» برداشته شد', 'این عنوان دیگر در فهرست ذخیره‌شده تو نیست.')
  if (props.slug) trackWatchlistAction({ id: props.id, slug: props.slug, type: props.contentType }, added)
}
</script>

<template>
  <button
    type="button"
    class="inline-flex items-center justify-center gap-2 rounded-xl font-black transition active:scale-95"
    :class="[
    iconOnly ? 'h-11 w-11' : compactOnMobile ? 'h-12 w-12 px-0 text-sm sm:h-auto sm:w-auto sm:px-4 sm:py-3' : 'min-h-12 px-4 py-3 text-sm',
    saved ? 'bg-primary-500 text-night-950 hover:bg-primary-400' : dark ? 'bg-white/10 text-ink ring-1 ring-white/20 hover:bg-white/20 hover:ring-primary-400/25' : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40',
    ]"
    :aria-label="saved ? 'حذف از لیست من' : 'افزودن به لیست من'"
    :aria-pressed="saved"
    @click="handleToggle"
  >
    <CinematicIcon name="bookmark" class="size-5 transition-colors" :filled="saved" :stroke-width="saved ? 2.2 : 1.8" />
    <span v-if="!iconOnly" :class="compactOnMobile ? 'hidden sm:inline' : ''">{{ saved ? 'در لیست من' : 'افزودن به لیست من' }}</span>
  </button>
</template>
