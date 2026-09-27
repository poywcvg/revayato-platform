<script setup lang="ts">
/**
 * Bulk actions for a selection of titles.
 *
 * Grouped by what each verb *costs*, because that is what decides whether a
 * selection is reasonable. Changing publication state is a database write and
 * can run over hundreds of rows; a re-crawl only enqueues a job; verifying
 * probes the network inside the request, so the backend caps that selection at
 * twenty and this bar says so before the click rather than after the timeout.
 *
 * Results come back per title. A batch of fifty where three fail for three
 * different reasons is the normal case, so the summary lists the failures by
 * name instead of collapsing them into "۳ مورد ناموفق".
 */
import type { AdminContentKind, BulkResultRow } from '~/types/admin'
import Loader from '~icons/lucide/loader-circle'
import X from '~icons/lucide/x'

const props = defineProps<{ kind: AdminContentKind, ids: number[] }>()
const emit = defineEmits<{ done: []; clear: [] }>()

const { bulk } = useAdminOps()
const notify = useNotifications()

const running = ref('')
const failures = ref<BulkResultRow[]>([])
const fa = (n: number) => n.toLocaleString('fa-IR')

interface Verb { action: string, label: string, confirm?: string, slow?: boolean, tone?: 'danger' }

/** `slow` mirrors the backend's BULK_SLOW set (network inside the request). */
const VERBS: Verb[] = [
  { action: 'publish', label: 'انتشار' },
  { action: 'unpublish', label: 'پیش‌نویس' },
  { action: 'archive', label: 'بایگانی', confirm: 'بایگانی شوند؟', tone: 'danger' },
  { action: 'recrawl', label: 'جستجوی دوباره' },
  { action: 'refresh_subtitles', label: 'استخراج زیرنویس' },
  { action: 'verify', label: 'تست منابع', slow: true },
  { action: 'sync_tmdb', label: 'هم‌گام با TMDB', slow: true },
  { action: 'prune_dead', label: 'پاکسازی لینک مرده' },
  { action: 'strip_contaminated', label: 'حذف لینک ناهمخوان' },
  { action: 'resolve_gaps', label: 'بستن مشکلات' },
]

const SLOW_LIMIT = 20
function tooMany(verb: Verb) {
  return !!verb.slow && props.ids.length > SLOW_LIMIT
}

async function run(verb: Verb) {
  if (running.value || !props.ids.length) return
  if (verb.confirm && !window.confirm(`${fa(props.ids.length)} عنوان ${verb.confirm}`)) return
  running.value = verb.action
  failures.value = []
  try {
    const response = await bulk(props.kind, props.ids, verb.action)
    failures.value = response.results.filter(row => !row.ok)
    if (response.failed) {
      notify.error(
        `${verb.label}: ${fa(response.succeeded)} موفق، ${fa(response.failed)} ناموفق`,
        'جزئیات زیر فهرست آمده است',
      )
    }
    else {
      notify.success(verb.label, `${fa(response.succeeded)} عنوان انجام شد`)
    }
    emit('done')
  }
  catch (err) {
    const data = (err as { data?: { code?: string, detail?: string } })?.data
    notify.error('انجام نشد', data?.detail || 'سرور درخواست را نپذیرفت')
  }
  finally { running.value = '' }
}

/** Why a failed title failed, in words the panel already uses elsewhere. */
const ERROR_LABEL: Record<string, string> = {
  not_found: 'یافت نشد',
  publish_blocked: 'شرایط انتشار کامل نیست',
  queue_failed: 'صف در دسترس نبود',
  action_failed: 'اجرا با خطا مواجه شد',
  no_tmdb_id: 'شناسهٔ TMDB ندارد',
}
</script>

<template>
  <div
    v-if="ids.length"
    class="sticky bottom-3 z-20 rounded-[var(--rv-radius)] border border-[var(--rv-border)] bg-[var(--rv-surface-2)] p-3 shadow-lg"
  >
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs font-black text-[var(--rv-text)]">{{ fa(ids.length) }} انتخاب‌شده</span>
      <button type="button" class="rv-icon-btn rv-focus" title="لغو انتخاب" @click="emit('clear')">
        <X class="size-4" />
      </button>
      <span class="h-4 w-px bg-[var(--rv-border)]" />
      <button
        v-for="verb in VERBS" :key="verb.action" type="button"
        class="rv-btn rv-focus !min-h-8 !px-2.5 !text-xs"
        :class="verb.tone === 'danger' ? 'rv-btn--subtle' : 'rv-btn--ghost'"
        :style="verb.tone === 'danger' ? { color: 'var(--rv-danger)' } : {}"
        :disabled="!!running || tooMany(verb)"
        :title="tooMany(verb) ? `این عملیات شبکه را برای هر عنوان صدا می‌زند؛ حداکثر ${fa(SLOW_LIMIT)} عنوان` : verb.label"
        @click="run(verb)"
      >
        <Loader v-if="running === verb.action" class="size-3.5 animate-spin" />
        {{ verb.label }}
      </button>
    </div>

    <ul v-if="failures.length" class="mt-2 max-h-28 overflow-y-auto border-t border-[var(--rv-border)] pt-2 text-xs">
      <li v-for="row in failures" :key="row.id" class="flex items-center gap-2 py-0.5">
        <span class="font-black" :style="{ color: 'var(--rv-danger)' }">{{ row.title || row.id }}</span>
        <span class="font-semibold text-[var(--rv-muted)]">{{ ERROR_LABEL[row.error || ''] || row.error }}</span>
      </li>
    </ul>
  </div>
</template>
