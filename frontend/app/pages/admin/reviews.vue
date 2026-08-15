<script setup lang="ts">
import Eye from '~icons/lucide/eye'
import EyeOff from '~icons/lucide/eye-off'
import MessageSquare from '~icons/lucide/message-square-text'
import Refresh from '~icons/lucide/rotate-cw'
import Search from '~icons/lucide/search'
import type { AdminReviewItem, AppErrorDetails } from '~/types'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'مدیریت دیدگاه‌ها', robots: 'noindex, nofollow' })

const api = useAdminReviews()
const notifications = useNotifications()

const reviews = ref<AdminReviewItem[]>([])
const total = ref(0)
const loading = ref(true)
const savingId = ref<number | null>(null)
const error = ref<AppErrorDetails | null>(null)
const pageSize = 20
type ReviewFilters = { q: string; content_type: string; hidden: string }
const {
  filters,
  page,
  debouncedWatch,
  syncQuery,
  clearFilters,
} = useDebouncedFilters<ReviewFilters>({
  q: '',
  content_type: '',
  hidden: '',
}, {
  urlKeys: ['q', 'content_type', 'hidden'],
})
const filterDefaults = { q: '', content_type: '', hidden: '' }

async function loadReviews(silent = false) {
  if (!silent) loading.value = true
  try {
    const response = await api.list({
      q: filters.q,
      content_type: filters.content_type || undefined,
      hidden: filters.hidden as '' | 'true' | 'false' | undefined,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    reviews.value = response.results
    total.value = response.count
    error.value = null
  } catch (cause) {
    if (!silent) error.value = getAppError(cause, 'فهرست دیدگاه‌ها دریافت نشد.')
  } finally {
    if (!silent) loading.value = false
  }
}

async function toggleHidden(review: AdminReviewItem) {
  savingId.value = review.id
  try {
    const updated = await api.setHidden(review.id, !review.is_hidden)
    const index = reviews.value.findIndex(item => item.id === review.id)
    if (index >= 0) reviews.value[index] = updated
    notifications.success(
      updated.is_hidden ? 'نظر مخفی شد' : 'نظر نمایش داده شد',
      updated.is_hidden ? 'از صفحه عمومی حذف شد.' : 'دوباره برای کاربران دیده می‌شود.',
    )
  } catch (cause) {
    notifications.notifyError(cause, 'تغییر وضعیت نظر انجام نشد.')
  } finally {
    savingId.value = null
  }
}

function contentHref(review: AdminReviewItem) {
  if (!review.content?.slug) return null
  return review.content_type === 'series'
    ? `/series/${review.content.slug}`
    : `/movies/${review.content.slug}`
}

debouncedWatch(() => {
  syncQuery()
  void loadReviews()
}, [() => filters.content_type, () => filters.hidden])

watch(page, () => {
  syncQuery()
  void loadReviews()
})
onMounted(() => { void loadReviews() })
</script>

<template>
  <div class="space-y-5 px-4 py-5 sm:px-6 lg:px-8">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p class="text-[11px] font-black text-[var(--admin-muted)]">محتوای کاربران</p>
        <h1 class="mt-1 text-2xl font-black">مدیریت دیدگاه‌ها</h1>
        <p class="mt-1 text-xs text-[var(--admin-muted)]">{{ total.toLocaleString('fa-IR') }} نظر ثبت‌شده</p>
      </div>
      <AdminButton variant="secondary" :disabled="loading" @click="loadReviews()">
        <Refresh class="size-4" />بروزرسانی
      </AdminButton>
    </div>

    <AdminCard>
      <div class="grid gap-3 md:grid-cols-3">
        <label class="relative">
          <Search class="pointer-events-none absolute end-3 top-1/2 size-4 -translate-y-1/2 text-[var(--admin-muted)]" />
          <input v-model="filters.q" class="admin-input w-full pe-10" placeholder="جستجو در متن یا نام کاربر…">
        </label>
        <select v-model="filters.content_type" class="admin-input">
          <option value="">فیلم و سریال</option>
          <option value="movie">فقط فیلم</option>
          <option value="series">فقط سریال</option>
        </select>
        <select v-model="filters.hidden" class="admin-input">
          <option value="">همه دیدگاه‌ها</option>
          <option value="false">نمایش‌داده‌شده</option>
          <option value="true">مخفی‌شده</option>
        </select>
        <button
          v-if="filters.q || filters.content_type || filters.hidden"
          type="button"
          class="admin-focus inline-flex min-h-11 items-center self-end rounded-lg px-2 text-xs font-bold text-[var(--admin-accent)] hover:underline"
          @click="clearFilters(filterDefaults)"
        >
          پاک کردن فیلترها
        </button>
      </div>
    </AdminCard>

    <AdminState v-if="loading" title="در حال بارگذاری دیدگاه‌ها…" message="لطفاً چند لحظه صبر کنید." />
    <AdminState v-else-if="error" kind="error" :title="error.message" message="فهرست دیدگاه‌ها دریافت نشد." @retry="loadReviews()" />

    <div v-else class="space-y-3">
      <AdminCard v-for="review in reviews" :key="review.id" class="!p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="grid size-9 place-items-center rounded-xl bg-[var(--admin-surface-muted)] text-[var(--admin-primary)]">
                <MessageSquare class="size-4" />
              </span>
              <div class="min-w-0">
                <p class="truncate text-sm font-black">{{ review.username }}</p>
                <p class="text-[11px] text-[var(--admin-muted)]">
                  امتیاز {{ Number(review.score).toLocaleString('fa-IR') }}/۱۰
                  · {{ review.content_type === 'series' ? 'سریال' : 'فیلم' }}
                  <template v-if="review.content">
                    ·
                    <NuxtLink v-if="contentHref(review)" :to="contentHref(review)!" class="text-[var(--admin-primary)] hover:underline" target="_blank">
                      {{ review.content.title }}
                    </NuxtLink>
                    <span v-else>{{ review.content.title }}</span>
                  </template>
                </p>
              </div>
            </div>
            <p class="mt-3 text-sm leading-7 text-[var(--admin-text)]">{{ review.review }}</p>
            <div class="mt-2 flex flex-wrap gap-2 text-[10px] font-bold">
              <AdminBadge v-if="review.is_spoiler">اسپویلر</AdminBadge>
              <AdminBadge v-if="review.is_hidden">مخفی</AdminBadge>
            </div>
          </div>
          <AdminButton
            variant="secondary"
            size="sm"
            :disabled="savingId === review.id"
            @click="toggleHidden(review)"
          >
            <EyeOff v-if="!review.is_hidden" class="size-4" />
            <Eye v-else class="size-4" />
            {{ review.is_hidden ? 'نمایش' : 'مخفی‌کردن' }}
          </AdminButton>
        </div>
      </AdminCard>

      <AdminCard v-if="!reviews.length" class="grid place-items-center py-12 text-sm text-[var(--admin-muted)]">
        دیدگاهی با این فیلتر پیدا نشد.
      </AdminCard>

      <AdminPagination
        :page="page"
        :total="total"
        :page-size="pageSize"
        :loading="loading"
        @update:page="page = $event"
      />
    </div>
  </div>
</template>
