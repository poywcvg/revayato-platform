<script setup lang="ts">
import Archive from '~icons/lucide/archive'
import Edit from '~icons/lucide/pencil-line'
import Eye from '~icons/lucide/eye'
import FilePen from '~icons/lucide/file-pen-line'
import Globe from '~icons/lucide/globe'
import Refresh from '~icons/lucide/rotate-cw'
import type { AdminMovie } from '~/types'

defineProps<{ movies: AdminMovie[]; loading?: boolean }>()
defineEmits<{
  edit: [movie: AdminMovie]
  preview: [movie: AdminMovie]
  sync: [movie: AdminMovie]
  publish: [movie: AdminMovie]
  draft: [movie: AdminMovie]
  archive: [movie: AdminMovie]
}>()

const statusLabel = { draft: 'پیش‌نویس', published: 'منتشرشده', archived: 'آرشیوشده' }
function dateLabel(value: string) {
  return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium' }).format(new Date(value))
}
function ratingLabel(movie: AdminMovie) {
  return movie.imdb_rating || movie.rating_average || '—'
}
</script>

<template>
  <div class="overflow-hidden">
    <div v-if="loading" class="divide-y divide-[var(--admin-border)]" aria-label="در حال بارگذاری فیلم‌ها">
      <div v-for="item in 7" :key="item" class="flex animate-pulse items-center gap-4 px-5 py-4">
        <span class="h-16 w-11 shrink-0 rounded-lg bg-[var(--admin-surface-muted)]" />
        <span class="h-4 max-w-44 flex-1 rounded bg-[var(--admin-surface-muted)]" />
        <span class="mr-auto h-8 w-28 shrink-0 rounded bg-[var(--admin-surface-muted)]" />
      </div>
    </div>

    <div v-else>
      <div class="responsive-table hidden md:block">
        <table class="w-full min-w-[1040px] border-collapse text-right text-sm">
          <thead>
            <tr class="border-b border-[var(--admin-border)] bg-[var(--admin-surface-muted)]/55 text-xs text-[var(--admin-muted)]">
              <th class="px-5 py-3.5 font-extrabold">فیلم</th>
              <th class="px-4 py-3.5 font-extrabold">وضعیت</th>
              <th class="px-4 py-3.5 font-extrabold">شناسه‌ها</th>
              <th class="px-4 py-3.5 font-extrabold">امتیاز</th>
              <th class="px-4 py-3.5 font-extrabold">آخرین ویرایش</th>
              <th class="px-5 py-3.5 text-left font-extrabold">عملیات</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-[var(--admin-border)]">
            <tr
              v-for="movie in movies"
              :key="movie.id"
              class="group cursor-pointer hover:bg-[var(--admin-warm)]/12"
              @click="$emit('edit', movie)"
            >
              <td class="px-5 py-3">
                <div class="flex items-center gap-3">
                  <div class="h-16 w-11 shrink-0 overflow-hidden rounded-lg border border-[var(--admin-border)] bg-[var(--admin-surface-muted)]">
                    <img v-if="movie.poster_url" :src="movie.poster_url" :alt="`پوستر ${movie.title}`" width="88" height="128" loading="lazy" class="h-full w-full object-cover">
                  </div>
                  <div class="min-w-0">
                    <p class="max-w-72 truncate font-black text-[var(--admin-text)] group-hover:text-[var(--admin-primary)]">{{ movie.title }}</p>
                    <p class="mt-0.5 max-w-72 truncate text-xs text-[var(--admin-muted)]" dir="ltr">{{ movie.original_title || '—' }}</p>
                    <p class="mt-1 text-[11px] text-[var(--admin-muted)]">{{ movie.release_year || 'سال نامشخص' }}</p>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3"><AdminBadge :tone="movie.publication_status">{{ statusLabel[movie.publication_status] }}</AdminBadge></td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1.5">
                  <AdminBadge v-if="movie.tmdb_id" tone="tmdb">TMDB {{ movie.tmdb_id }}</AdminBadge>
                  <span v-if="movie.imdb_id" class="rounded-md bg-[var(--admin-sidebar)]/7 px-2 py-1 font-mono text-[10px] text-[var(--admin-primary)]">{{ movie.imdb_id }}</span>
                  <span v-if="!movie.tmdb_id && !movie.imdb_id" class="text-xs text-[var(--admin-muted)]">ثبت نشده</span>
                </div>
              </td>
              <td class="px-4 py-3 font-latin text-xs font-bold">{{ ratingLabel(movie) }}</td>
              <td class="px-4 py-3 text-xs text-[var(--admin-muted)]">{{ dateLabel(movie.updated_at) }}</td>
              <td class="px-5 py-3" @click.stop>
                <div class="flex justify-end gap-1">
                  <button type="button" class="admin-focus grid size-11 place-items-center rounded-lg text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)] hover:text-[var(--admin-primary)]" title="ویرایش" aria-label="ویرایش فیلم" @click="$emit('edit', movie)"><Edit class="size-4" /></button>
                  <button type="button" class="admin-focus grid size-11 place-items-center rounded-lg text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)] hover:text-[var(--admin-primary)]" title="نمایش در سایت" aria-label="نمایش فیلم" @click="$emit('preview', movie)"><Eye class="size-4" /></button>
                  <button type="button" :disabled="!movie.tmdb_id" class="admin-focus grid size-11 place-items-center rounded-lg text-[var(--admin-muted)] hover:bg-teal-50 hover:text-teal-800 disabled:cursor-not-allowed disabled:opacity-30" title="همگام‌سازی TMDB" aria-label="همگام‌سازی با TMDB" @click="$emit('sync', movie)"><Refresh class="size-4" /></button>
                  <button type="button" :disabled="movie.publication_status === 'published'" class="admin-focus grid size-11 place-items-center rounded-lg text-[var(--admin-muted)] hover:bg-emerald-50 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-30" title="انتشار" aria-label="انتشار فیلم" @click="$emit('publish', movie)"><Globe class="size-4" /></button>
                  <button type="button" :disabled="movie.publication_status === 'draft'" class="admin-focus grid size-11 place-items-center rounded-lg text-[var(--admin-muted)] hover:bg-amber-50 hover:text-amber-800 disabled:cursor-not-allowed disabled:opacity-30" title="پیش‌نویس" aria-label="تبدیل به پیش‌نویس" @click="$emit('draft', movie)"><FilePen class="size-4" /></button>
                  <button type="button" :disabled="movie.publication_status === 'archived'" class="admin-focus grid size-11 place-items-center rounded-lg text-[var(--admin-muted)] hover:bg-red-50 hover:text-[var(--admin-danger)] disabled:cursor-not-allowed disabled:opacity-30" title="حذف فیلم از سایت" aria-label="حذف فیلم از سایت" @click="$emit('archive', movie)"><Archive class="size-4" /></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="divide-y divide-[var(--admin-border)] md:hidden">
        <article v-for="movie in movies" :key="movie.id" class="p-4">
          <button type="button" class="admin-focus flex w-full gap-3 text-right" @click="$emit('edit', movie)">
            <div class="h-24 w-16 shrink-0 overflow-hidden rounded-xl bg-[var(--admin-surface-muted)]">
              <img v-if="movie.poster_url" :src="movie.poster_url" :alt="`پوستر ${movie.title}`" loading="lazy" class="h-full w-full object-cover">
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <h3 class="truncate font-black">{{ movie.title }}</h3>
                  <p class="mt-0.5 truncate text-xs text-[var(--admin-muted)]">{{ movie.original_title }}</p>
                </div>
                <AdminBadge class="shrink-0" :tone="movie.publication_status">{{ statusLabel[movie.publication_status] }}</AdminBadge>
              </div>
              <div class="mt-3 flex items-center gap-2 text-xs text-[var(--admin-muted)]">
                <span>{{ movie.release_year || '—' }}</span>
                <span>•</span>
                <span>امتیاز {{ ratingLabel(movie) }}</span>
              </div>
            </div>
          </button>
          <div class="mt-3 flex flex-wrap gap-1.5">
            <button type="button" class="admin-focus min-h-11 rounded-lg bg-[var(--admin-primary)] px-3 py-2 text-xs font-bold text-white" @click="$emit('edit', movie)">ویرایش</button>
            <button type="button" class="admin-focus min-h-11 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800 disabled:opacity-40" :disabled="movie.publication_status === 'published'" @click="$emit('publish', movie)">انتشار</button>
            <button type="button" class="admin-focus min-h-11 rounded-lg bg-amber-50 px-3 py-2 text-xs font-bold text-amber-900 disabled:opacity-40" :disabled="movie.publication_status === 'draft'" @click="$emit('draft', movie)">پیش‌نویس</button>
            <button type="button" class="admin-focus min-h-11 rounded-lg bg-[var(--admin-surface-muted)] px-3 py-2 text-xs font-bold" @click="$emit('preview', movie)">نمایش</button>
            <button v-if="movie.tmdb_id" type="button" class="admin-focus min-h-11 rounded-lg px-3 py-2 text-xs font-bold text-teal-800 hover:bg-teal-50" @click="$emit('sync', movie)">همگام‌سازی</button>
            <button type="button" class="admin-focus ms-auto grid size-11 place-items-center rounded-lg text-[var(--admin-danger)] hover:bg-red-50" aria-label="حذف از سایت" :disabled="movie.publication_status === 'archived'" @click="$emit('archive', movie)"><Archive class="size-4" /></button>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>
