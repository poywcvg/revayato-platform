<script setup lang="ts">
import type { AdminReviewItem } from '~/types/admin'
import MessageSquare from '~icons/lucide/message-square'
import Search from '~icons/lucide/search'
import Star from '~icons/lucide/star'
import Sparkles from '~icons/lucide/sparkles'
import ShieldCheck from '~icons/lucide/shield-check'
import Eye from '~icons/lucide/eye'
import EyeOff from '~icons/lucide/eye-off'
import Send from '~icons/lucide/send-horizontal'
import ChevronRight from '~icons/lucide/chevron-right'
import ChevronLeft from '~icons/lucide/chevron-left'
import Inbox from '~icons/lucide/inbox'
import CheckCheck from '~icons/lucide/check-check'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'مدیریت نقدها — روایتو' })

const { listReviews, updateReview, refreshOverview } = useAdminInteraction()
const notify = useNotifications()

const PAGE_SIZE = 20
const q = ref('')
const qDebounced = ref('')
const contentType = ref<'' | 'movie' | 'series'>('')
const state = ref<'' | 'unanswered' | 'answered' | 'featured'>('')
const hidden = ref<'' | 'true' | 'false'>('')
const offset = ref(0)

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(q, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { qDebounced.value = val.trim(); offset.value = 0 }, 350)
})
watch([contentType, state, hidden], () => { offset.value = 0 })

const { data, pending, error, refresh } = await useAsyncData(
  'admin-reviews',
  () => listReviews({
    content_type: contentType.value || undefined,
    state: state.value || undefined,
    hidden: hidden.value || undefined,
    q: qDebounced.value || undefined,
    limit: PAGE_SIZE,
    offset: offset.value,
  }),
  { watch: [qDebounced, contentType, state, hidden, offset] },
)

const rows = computed(() => data.value?.results ?? [])
const total = computed(() => data.value?.count ?? 0)
const counts = computed(() => data.value?.counts ?? null)
const from = computed(() => (total.value === 0 ? 0 : offset.value + 1))
const to = computed(() => Math.min(offset.value + PAGE_SIZE, total.value))
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

const STATE_TABS = [
  { value: '', label: 'همه', key: 'total' as const },
  { value: 'unanswered', label: 'بی‌پاسخ', key: 'unanswered' as const },
  { value: 'answered', label: 'پاسخ‌داده', key: 'answered' as const },
  { value: 'featured', label: 'برگزیده', key: 'featured' as const },
]

function scoreOf(r: AdminReviewItem) { return Math.round(Number(r.score) || 0) }
function dateOf(iso: string) {
  try { return new Intl.DateTimeFormat('fa-IR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso)) }
  catch { return '—' }
}
function detailHref(r: AdminReviewItem) {
  if (!r.content) return undefined
  return r.content.content_type === 'series' ? `/series/${r.content.slug}` : `/movies/${r.content.slug}`
}

// Per-review busy + reply-draft state.
const busy = ref<Record<number, boolean>>({})
const replyOpen = ref<Record<number, boolean>>({})
const replyDraft = ref<Record<number, string>>({})

async function apply(r: AdminReviewItem, payload: Record<string, unknown>, okMsg: string) {
  busy.value = { ...busy.value, [r.id]: true }
  try {
    await updateReview(r.id, payload)
    notify.success('انجام شد', okMsg)
    await Promise.all([refresh(), refreshOverview()])
  } catch (err) {
    notify.notifyError(err, 'عملیات روی نقد ممکن نشد.')
  } finally {
    busy.value = { ...busy.value, [r.id]: false }
  }
}

function toggleHide(r: AdminReviewItem) {
  apply(r, { is_hidden: !r.is_hidden }, r.is_hidden ? 'نقد دوباره نمایش داده شد' : 'نقد پنهان شد')
}
function toggleFeature(r: AdminReviewItem) {
  apply(r, { is_featured: !r.is_featured }, r.is_featured ? 'از برگزیده‌ها خارج شد' : 'به‌عنوان نقد برگزیده انتخاب شد')
}

function openReply(r: AdminReviewItem) {
  replyDraft.value = { ...replyDraft.value, [r.id]: r.admin_reply || '' }
  replyOpen.value = { ...replyOpen.value, [r.id]: true }
}
function cancelReply(r: AdminReviewItem) {
  replyOpen.value = { ...replyOpen.value, [r.id]: false }
}
async function saveReply(r: AdminReviewItem) {
  const body = (replyDraft.value[r.id] ?? '').trim()
  await apply(r, { admin_reply: body }, body ? 'پاسخ روایتو ثبت شد' : 'پاسخ حذف شد')
  replyOpen.value = { ...replyOpen.value, [r.id]: false }
}

onMounted(() => { void refreshOverview() })
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">نقدها</h1>
      <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">مدیریت دیدگاه‌های کاربران، پاسخ عمومی روایتو و انتخاب نقدهای برگزیده</p>
    </div>

    <!-- Summary tiles -->
    <div class="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-5">
      <RvStat label="کل نقدها" :value="counts?.total ?? null" :icon="MessageSquare" tone="accent" :loading="pending && !counts" />
      <RvStat label="بی‌پاسخ" :value="counts?.unanswered ?? null" :icon="Inbox" tone="warning" :loading="pending && !counts" />
      <RvStat label="پاسخ‌داده" :value="counts?.answered ?? null" :icon="CheckCheck" tone="success" :loading="pending && !counts" />
      <RvStat label="برگزیده" :value="counts?.featured ?? null" :icon="Sparkles" tone="violet" :loading="pending && !counts" />
      <RvStat label="پنهان" :value="counts?.hidden ?? null" :icon="EyeOff" tone="danger" :loading="pending && !counts" />
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-center gap-3">
      <div class="inline-flex rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-2)] p-1">
        <button
          v-for="tab in STATE_TABS"
          :key="tab.value"
          type="button"
          class="rv-focus rounded-[calc(var(--rv-radius-sm)-2px)] px-3 py-1.5 text-xs font-black transition"
          :class="state === tab.value ? 'bg-[var(--rv-accent)] text-[var(--rv-on-accent)]' : 'text-[var(--rv-muted)] hover:text-[var(--rv-text)]'"
          @click="state = tab.value as typeof state"
        >
          {{ tab.label }}
          <span v-if="counts" class="opacity-70">({{ fa(counts[tab.key]) }})</span>
        </button>
      </div>
      <div class="relative min-w-[180px] flex-1">
        <Search class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--rv-faint)]" />
        <input v-model="q" type="search" placeholder="جستجو در متن نقد یا نام کاربر…" class="rv-input !pr-9">
      </div>
      <select v-model="contentType" class="rv-input !w-auto">
        <option value="">همهٔ آثار</option>
        <option value="movie">فیلم‌ها</option>
        <option value="series">سریال‌ها</option>
      </select>
      <select v-model="hidden" class="rv-input !w-auto">
        <option value="">نمایش‌داده و پنهان</option>
        <option value="false">فقط نمایش‌داده</option>
        <option value="true">فقط پنهان</option>
      </select>
    </div>

    <RvPanel :icon="MessageSquare" :padded="false">
      <template #actions>
        <span v-if="total" class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
      </template>

      <RvState v-if="error" kind="error" title="خطا در دریافت نقدها" @retry="refresh()" />
      <RvState v-else-if="!pending && rows.length === 0" title="نقدی یافت نشد" message="با فیلترهای دیگری امتحان کنید." />

      <div v-else-if="pending && rows.length === 0" class="space-y-3 p-4">
        <div v-for="n in 4" :key="n" class="h-32 animate-pulse rounded-[var(--rv-radius)] bg-[var(--rv-surface-2)]" />
      </div>

      <ul v-else class="divide-y divide-[var(--rv-border)]">
        <li v-for="r in rows" :key="r.id" class="p-4" :class="r.is_hidden ? 'opacity-70' : ''">
          <div class="flex gap-3.5">
            <!-- Poster -->
            <NuxtLink v-if="r.content" :to="detailHref(r)" class="rv-focus shrink-0" target="_blank">
              <img
                v-if="r.content.poster"
                :src="r.content.poster"
                :alt="r.content.title"
                class="h-24 w-16 rounded-[var(--rv-radius-sm)] object-cover ring-1 ring-[var(--rv-border)]"
                loading="lazy"
              >
              <span v-else class="grid h-24 w-16 place-items-center rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-3)] text-[var(--rv-faint)]">
                <MessageSquare class="size-5" />
              </span>
            </NuxtLink>

            <div class="min-w-0 flex-1">
              <!-- Title + badges -->
              <div class="flex flex-wrap items-center gap-2">
                <NuxtLink v-if="r.content" :to="detailHref(r)" target="_blank" class="rv-focus truncate text-sm font-black text-[var(--rv-text)] hover:text-[var(--rv-accent)]">
                  {{ r.content.title }}
                </NuxtLink>
                <span v-else class="text-sm font-black text-[var(--rv-faint)]">اثر حذف‌شده</span>
                <RvBadge tone="neutral">{{ r.content_type === 'series' ? 'سریال' : 'فیلم' }}</RvBadge>
                <RvBadge v-if="r.is_featured" tone="violet"><Sparkles class="size-3" /> برگزیده</RvBadge>
                <RvBadge v-if="r.is_hidden" tone="danger"><EyeOff class="size-3" /> پنهان</RvBadge>
                <RvBadge v-if="r.is_spoiler" tone="warning">اسپویل</RvBadge>
              </div>

              <!-- Meta -->
              <div class="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs font-semibold text-[var(--rv-muted)]">
                <span class="inline-flex items-center gap-1 text-[var(--rv-warning)]">
                  <Star class="size-3.5 fill-current" /><span class="tabular-nums">{{ fa(scoreOf(r)) }}</span>
                  <span class="text-[var(--rv-faint)]">/ ۱۰</span>
                </span>
                <span aria-hidden="true">·</span>
                <span>{{ r.username }}</span>
                <span aria-hidden="true">·</span>
                <span>{{ dateOf(r.created_at) }}</span>
              </div>

              <!-- Review body -->
              <p class="mt-2 whitespace-pre-wrap break-words text-[13px] leading-7 text-[var(--rv-text)]">{{ r.review }}</p>

              <!-- Existing admin reply -->
              <div v-if="r.admin_reply && !replyOpen[r.id]" class="mt-3 rounded-[var(--rv-radius-sm)] border-r-2 border-[var(--rv-accent)] bg-[var(--rv-accent-soft)] px-3 py-2">
                <p class="flex items-center gap-1.5 text-xs font-black text-[var(--rv-accent)]">
                  <ShieldCheck class="size-3.5" /> پاسخ روایتو
                </p>
                <p class="mt-1 whitespace-pre-wrap break-words text-xs leading-6 text-[var(--rv-text)]">{{ r.admin_reply }}</p>
              </div>

              <!-- Reply composer -->
              <div v-if="replyOpen[r.id]" class="mt-3">
                <textarea
                  v-model="replyDraft[r.id]"
                  rows="3"
                  maxlength="4000"
                  placeholder="پاسخ عمومی روایتو زیر این نقد نمایش داده می‌شود…"
                  class="rv-input !h-auto w-full resize-y !py-2.5 leading-7"
                />
                <div class="mt-2 flex items-center gap-2">
                  <button type="button" class="rv-btn rv-btn--primary rv-focus !min-h-9" :disabled="busy[r.id]" @click="saveReply(r)">
                    <Send class="size-4" /> ثبت پاسخ
                  </button>
                  <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="busy[r.id]" @click="cancelReply(r)">
                    انصراف
                  </button>
                </div>
              </div>

              <!-- Actions -->
              <div v-else class="mt-3 flex flex-wrap items-center gap-2">
                <button type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-9" :disabled="busy[r.id]" @click="openReply(r)">
                  <ShieldCheck class="size-4" /> {{ r.admin_reply ? 'ویرایش پاسخ' : 'پاسخ روایتو' }}
                </button>
                <button
                  type="button"
                  class="rv-btn rv-btn--subtle rv-focus !min-h-9"
                  :disabled="busy[r.id]"
                  :style="r.is_featured ? { color: 'var(--rv-violet)' } : {}"
                  @click="toggleFeature(r)"
                >
                  <Sparkles class="size-4" /> {{ r.is_featured ? 'حذف از برگزیده' : 'برگزیده' }}
                </button>
                <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="busy[r.id]" @click="toggleHide(r)">
                  <component :is="r.is_hidden ? Eye : EyeOff" class="size-4" /> {{ r.is_hidden ? 'نمایش' : 'پنهان‌کردن' }}
                </button>
              </div>
            </div>
          </div>
        </li>
      </ul>

      <!-- Pagination -->
      <div v-if="total > PAGE_SIZE" class="flex items-center justify-between gap-3 border-t border-[var(--rv-border)] px-4 py-3">
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="offset === 0" @click="offset = Math.max(0, offset - PAGE_SIZE)">
          <ChevronRight class="size-4" /> قبلی
        </button>
        <span class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="to >= total" @click="offset = offset + PAGE_SIZE">
          بعدی <ChevronLeft class="size-4" />
        </button>
      </div>
    </RvPanel>
  </div>
</template>
