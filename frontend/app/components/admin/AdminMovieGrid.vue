<script setup lang="ts">
import Archive from '~icons/lucide/archive'
import Edit from '~icons/lucide/pencil-line'
import Eye from '~icons/lucide/eye'
import FilePen from '~icons/lucide/file-pen-line'
import Globe from '~icons/lucide/globe'
import Refresh from '~icons/lucide/rotate-cw'
import type { AdminMovie } from '~/types'

defineProps<{ movies: AdminMovie[] }>()
defineEmits<{
  edit: [movie: AdminMovie]
  preview: [movie: AdminMovie]
  sync: [movie: AdminMovie]
  publish: [movie: AdminMovie]
  draft: [movie: AdminMovie]
  archive: [movie: AdminMovie]
}>()

const statusLabel = { draft: 'پیش‌نویس', published: 'منتشرشده', archived: 'آرشیوشده' }
function ratingLabel(movie: AdminMovie) {
  return movie.imdb_rating || movie.rating_average || null
}
</script>

<template>
  <div class="admin-movie-grid p-4 xl:p-5">
    <article
      v-for="movie in movies"
      :key="movie.id"
      class="group min-w-0 overflow-hidden rounded-2xl border border-[var(--admin-border)] bg-[var(--admin-surface)] shadow-sm transition hover:-translate-y-0.5 hover:shadow-[var(--admin-shadow)]"
    >
      <button
        type="button"
        class="admin-focus relative block aspect-[2/3] w-full overflow-hidden bg-[var(--admin-surface-muted)] text-right"
        @click="$emit('edit', movie)"
      >
        <img
          v-if="movie.poster_url"
          :src="movie.poster_url"
          :alt="`پوستر ${movie.title}`"
          loading="lazy"
          width="320"
          height="480"
          class="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
        >
        <div v-else class="grid h-full place-items-center px-4 text-center text-xs font-bold text-[var(--admin-muted)]">
          پوستر ثبت نشده
        </div>
        <div class="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-[var(--admin-sidebar)]/90 to-transparent" />
        <AdminBadge class="absolute right-2 top-2" :tone="movie.publication_status">
          {{ statusLabel[movie.publication_status] }}
        </AdminBadge>
        <span
          v-if="ratingLabel(movie)"
          class="absolute bottom-2 left-2 rounded-lg bg-black/55 px-2 py-1 font-latin text-xs font-bold text-white"
        >
          ★ {{ ratingLabel(movie) }}
        </span>
        <div v-if="movie.is_dubbed || movie.has_subtitle" class="absolute bottom-2 right-2 flex gap-1">
          <span v-if="movie.is_dubbed" class="rounded-md bg-primary-500/90 px-1.5 py-0.5 text-[10px] font-black text-white" title="دوبله">دوبله</span>
          <span v-if="movie.has_subtitle" class="rounded-md bg-white/90 px-1.5 py-0.5 text-[10px] font-black text-[var(--admin-text)]" title="زیرنویس">زیرنویس</span>
        </div>
      </button>

      <div class="space-y-2.5 p-3">
        <div class="min-w-0">
          <h3 class="truncate text-sm font-black">{{ movie.title }}</h3>
          <p class="mt-0.5 truncate text-xs text-[var(--admin-muted)]">
            {{ movie.release_year || 'سال نامشخص' }} · {{ movie.metadata_source === 'tmdb' ? 'TMDB' : 'دستی' }}
          </p>
        </div>
        <div class="grid grid-cols-3 gap-1">
          <button type="button" class="admin-focus grid min-h-11 place-items-center rounded-lg bg-[var(--admin-surface-muted)] text-[var(--admin-primary)] hover:bg-[var(--admin-primary)] hover:text-white" title="ویرایش" aria-label="ویرایش" @click="$emit('edit', movie)"><Edit class="size-3.5" /></button>
          <button type="button" class="admin-focus grid min-h-11 place-items-center rounded-lg bg-emerald-50 text-emerald-700 disabled:opacity-30" title="انتشار" aria-label="انتشار" :disabled="movie.publication_status === 'published'" @click="$emit('publish', movie)"><Globe class="size-3.5" /></button>
          <button type="button" class="admin-focus grid min-h-11 place-items-center rounded-lg bg-amber-50 text-amber-800 disabled:opacity-30" title="پیش‌نویس" aria-label="پیش‌نویس" :disabled="movie.publication_status === 'draft'" @click="$emit('draft', movie)"><FilePen class="size-3.5" /></button>
          <button type="button" class="admin-focus grid min-h-11 place-items-center rounded-lg bg-[var(--admin-surface-muted)] text-[var(--admin-muted)] hover:bg-[var(--admin-primary)]/10 hover:text-[var(--admin-primary)]" title="نمایش" aria-label="نمایش" @click="$emit('preview', movie)"><Eye class="size-3.5" /></button>
          <button type="button" class="admin-focus grid min-h-11 place-items-center rounded-lg bg-[var(--admin-surface-muted)] text-[var(--admin-muted)] hover:bg-teal-50 hover:text-teal-800 disabled:opacity-30" title="همگام‌سازی" aria-label="همگام‌سازی" :disabled="!movie.tmdb_id" @click="$emit('sync', movie)"><Refresh class="size-3.5" /></button>
          <button type="button" class="admin-focus grid min-h-11 place-items-center rounded-lg bg-[var(--admin-surface-muted)] text-[var(--admin-muted)] hover:bg-red-50 hover:text-[var(--admin-danger)] disabled:opacity-30" title="حذف از سایت" aria-label="حذف از سایت" :disabled="movie.publication_status === 'archived'" @click="$emit('archive', movie)"><Archive class="size-3.5" /></button>
        </div>
      </div>
    </article>
  </div>
</template>

<style scoped>
.admin-movie-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 8rem), 1fr));
  gap: clamp(.75rem, 1.4vw, 1.25rem);
}

@media (min-width: 768px) {
  .admin-movie-grid {
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 9rem), 1fr));
  }
}
</style>
