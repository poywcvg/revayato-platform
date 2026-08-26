<script setup lang="ts">
import Building2 from '~icons/lucide/building-2'
import Clapperboard from '~icons/lucide/clapperboard'
import Layers from '~icons/lucide/layers'
import Pencil from '~icons/lucide/pencil'
import Plus from '~icons/lucide/plus'
import Refresh from '~icons/lucide/rotate-cw'
import Search from '~icons/lucide/search'
import Tags from '~icons/lucide/tag'
import Trash2 from '~icons/lucide/trash-2'
import UserRound from '~icons/lucide/user-round'
import UsersRound from '~icons/lucide/users-round'
import type { Component } from 'vue'
import type { TaxonomyEntity } from '~/types'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'مدیریت طبقه‌بندی‌ها', robots: 'noindex, nofollow' })

type Row = Record<string, unknown> & { id: number }

const tabs: Array<{ key: TaxonomyEntity, label: string, icon: Component }> = [
  { key: 'genres', label: 'ژانرها', icon: Clapperboard },
  { key: 'countries', label: 'کشورها', icon: Building2 },
  { key: 'tags', label: 'برچسب‌ها', icon: Tags },
  { key: 'actors', label: 'بازیگران', icon: UsersRound },
  { key: 'directors', label: 'کارگردانان', icon: UserRound },
]

const route = useRoute()
const router = useRouter()

function initialEntity(): TaxonomyEntity {
  const raw = String(route.query.entity || '')
  return tabs.some(tab => tab.key === raw) ? raw as TaxonomyEntity : 'genres'
}

const entity = ref<TaxonomyEntity>(initialEntity())

const api = useAdminTaxonomy()
const notifications = useNotifications()

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const pageSize = 20

type Filters = { q: string }
const {
  filters,
  page,
  debouncedWatch,
  syncQuery,
  clearFilters,
} = useDebouncedFilters<Filters>({ q: '' }, { urlKeys: ['q'] })

function titleFor(row: Row) {
  return String(row.title ?? row.name ?? '—')
}

function slugFor(row: Row) {
  return String(row.slug ?? row.code ?? '')
}

async function load(silent = false) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const response = await api.list(entity.value, {
      q: filters.q,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
      ordering: entity.value === 'genres' ? 'title' : 'name',
    })
    rows.value = response.results as unknown as Row[]
    total.value = response.count
  } catch (cause) {
    error.value = getAppError(cause, 'فهرست دریافت نشد.').message
  } finally {
    if (!silent) loading.value = false
  }
}

// ---- create / edit modal ----
const modalOpen = ref(false)
const editing = ref<Row | null>(null)
const form = reactive<Record<string, string>>({})
const photoFile = ref<File | null>(null)

const isPerson = computed(() => entity.value === 'actors' || entity.value === 'directors')
const primaryLabel = computed(() => tabs.find(tab => tab.key === entity.value)?.label || '')

function openCreate() {
  editing.value = null
  Object.keys(form).forEach(key => delete form[key])
  if (entity.value === 'genres') form.title = ''
  else if (entity.value === 'countries') { form.name = ''; form.code = '' }
  else if (entity.value === 'tags') form.name = ''
  else { form.name = ''; form.original_name = ''; form.birth_date = ''; form.birth_place = ''; form.biography = '' }
  photoFile.value = null
  modalOpen.value = true
}

function openEdit(row: Row) {
  editing.value = row
  Object.keys(form).forEach(key => delete form[key])
  for (const key of ['title', 'name', 'code', 'slug', 'description', 'original_name', 'birth_date', 'birth_place', 'biography']) {
    const value = row[key]
    if (value != null) form[key] = String(value)
  }
  photoFile.value = null
  modalOpen.value = true
}

function selectPhoto(event: Event) {
  const input = event.target as HTMLInputElement
  photoFile.value = input.files?.[0] || null
}

async function save() {
  saving.value = true
  try {
    let payload: Record<string, unknown> | FormData
    if (isPerson.value && photoFile.value) {
      payload = new FormData()
      for (const [key, value] of Object.entries(form)) {
        if (String(value ?? '').trim()) payload.append(key, String(value))
      }
      payload.append('photo', photoFile.value)
    } else {
      payload = {}
      for (const [key, value] of Object.entries(form)) {
        if (String(value ?? '').trim()) payload[key] = value
      }
    }
    if (editing.value) {
      await api.update(entity.value, editing.value.id, payload)
      notifications.success('ذخیره شد', `${titleFor(editing.value)} به‌روزرسانی شد.`)
    } else {
      await api.create(entity.value, payload)
      notifications.success('ایجاد شد', `مورد جدید به ${primaryLabel.value} اضافه شد.`)
    }
    modalOpen.value = false
    await load(true)
  } catch (cause) {
    notifications.notifyError(cause, 'ذخیره‌سازی انجام نشد.')
  } finally {
    saving.value = false
  }
}

// ---- delete confirm ----
const deleteTarget = ref<Row | null>(null)
const deleting = ref(false)

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await api.remove(entity.value, deleteTarget.value.id)
    notifications.success('حذف شد', `${titleFor(deleteTarget.value)} حذف شد.`)
    deleteTarget.value = null
    await load(true)
  } catch (cause) {
    notifications.notifyError(cause, 'حذف انجام نشد؛ ممکن است این مورد هنوز به محتوا متصل باشد.')
  } finally {
    deleting.value = false
  }
}

watch(entity, () => {
  page.value = 1
  router.replace({ query: { ...route.query, entity: entity.value, page: undefined } })
  void load()
})

debouncedWatch(() => {
  syncQuery()
  void load()
}, [])

watch(page, () => {
  syncQuery()
  void load()
})

onMounted(() => { void load() })
</script>

<template>
  <div class="space-y-5 px-4 py-5 sm:px-6 lg:px-8">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p class="text-[11px] font-black text-[var(--admin-muted)]">فراداده کاتالوگ</p>
        <h1 class="mt-1 text-2xl font-black">مدیریت طبقه‌بندی‌ها</h1>
        <p class="mt-1 text-xs text-[var(--admin-muted)]">
          {{ total.toLocaleString('fa-IR') }} مورد در «{{ primaryLabel }}»
        </p>
      </div>
      <div class="flex items-center gap-2">
        <AdminButton variant="secondary" :disabled="loading" @click="load()">
          <template #icon><Refresh class="size-4" /></template>
          بروزرسانی
        </AdminButton>
        <AdminButton data-testid="taxonomy-create" @click="openCreate">
          <template #icon><Plus class="size-4" /></template>
          افزودن
        </AdminButton>
      </div>
    </div>

    <nav class="flex max-w-full gap-1 overflow-x-auto rounded-2xl border border-[var(--admin-border)] bg-white p-1 shadow-[var(--admin-shadow)]" aria-label="انتخاب دستهٔ طبقه‌بندی">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="admin-focus inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl px-4 text-xs font-black transition"
        :class="entity === tab.key
          ? 'bg-[var(--admin-primary)] text-white'
          : 'text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)]'"
        :aria-current="entity === tab.key ? 'page' : undefined"
        @click="entity = tab.key"
      >
        <component :is="tab.icon" class="size-3.5" />
        {{ tab.label }}
      </button>
    </nav>

    <AdminCard>
      <label class="relative block">
        <Search class="pointer-events-none absolute end-3 top-1/2 size-4 -translate-y-1/2 text-[var(--admin-muted)]" />
        <input v-model="filters.q" class="admin-input w-full pe-10" placeholder="جستجو…">
      </label>
      <button
        v-if="filters.q"
        type="button"
        class="admin-focus mt-2 inline-flex min-h-9 items-center rounded-lg px-2 text-xs font-bold text-[var(--admin-accent)] hover:underline"
        @click="clearFilters({ q: '' })"
      >
        پاک کردن جستجو
      </button>
    </AdminCard>

    <AdminState v-if="loading" title="در حال بارگذاری…" message="لطفاً چند لحظه صبر کنید." />
    <AdminState v-else-if="error" kind="error" title="خطا در دریافت فهرست" :message="error" @retry="load()" />

    <AdminCard v-else-if="!rows.length" class="grid place-items-center py-12 text-sm text-[var(--admin-muted)]">
      موردی پیدا نشد.
    </AdminCard>

    <AdminCard v-else class="overflow-hidden !p-0">
      <ul class="divide-y divide-[var(--admin-border)]">
        <li v-for="row in rows" :key="row.id" class="flex items-center gap-3 px-4 py-3">
          <span class="grid size-10 shrink-0 place-items-center overflow-hidden rounded-xl bg-[var(--admin-surface-muted)] text-[var(--admin-primary)]">
            <img
              v-if="typeof row.photo === 'string' && row.photo"
              :src="row.photo"
              alt=""
              class="size-full object-cover"
              loading="lazy"
            >
            <component :is="(tabs.find(tab => tab.key === entity)?.icon || Layers) as Component" v-else class="size-4" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-black">{{ titleFor(row) }}</p>
            <p v-if="slugFor(row)" class="truncate text-[11px] text-[var(--admin-muted)]" dir="ltr">{{ slugFor(row) }}</p>
          </div>
          <span v-if="'popularity' in row && row.popularity != null" class="hidden text-[11px] font-bold tabular-nums text-[var(--admin-muted)] sm:block">
            محبوبیت {{ Number(row.popularity).toLocaleString('fa-IR') }}
          </span>
          <AdminButton variant="ghost" size="sm" :aria-label="`ویرایش ${titleFor(row)}`" @click="openEdit(row)">
            <Pencil class="size-4" />
          </AdminButton>
          <AdminButton variant="ghost" size="sm" :aria-label="`حذف ${titleFor(row)}`" @click="deleteTarget = row">
            <Trash2 class="size-4 text-[var(--admin-danger)]" />
          </AdminButton>
        </li>
      </ul>
      <AdminPagination
        :page="page"
        :total="total"
        :page-size="pageSize"
        :loading="loading"
        :count-label="` ${primaryLabel}`"
        @update:page="page = $event"
      />
    </AdminCard>

    <AdminModal
      :open="modalOpen"
      :title="editing ? `ویرایش «${titleFor(editing)}»` : `افزودن به ${primaryLabel}`"
      size="md"
      @close="modalOpen = false"
    >
      <form class="space-y-4 p-5 sm:p-6" @submit.prevent="save">
        <template v-if="entity === 'genres'">
          <label class="block space-y-1.5">
            <span class="text-xs font-black">عنوان ژانر *</span>
            <input v-model="form.title" required class="admin-input w-full">
          </label>
          <label class="block space-y-1.5">
            <span class="text-xs font-black">توضیحات</span>
            <textarea v-model="form.description" rows="3" class="admin-input w-full" />
          </label>
        </template>

        <template v-else-if="entity === 'countries'">
          <label class="block space-y-1.5">
            <span class="text-xs font-black">نام کشور *</span>
            <input v-model="form.name" required class="admin-input w-full">
          </label>
          <label class="block space-y-1.5">
            <span class="text-xs font-black">کد کشور</span>
            <input v-model="form.code" class="admin-input w-full" dir="ltr" maxlength="8" placeholder="IR">
          </label>
        </template>

        <template v-else-if="entity === 'tags'">
          <label class="block space-y-1.5">
            <span class="text-xs font-black">نام برچسب *</span>
            <input v-model="form.name" required class="admin-input w-full">
          </label>
        </template>

        <template v-else>
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="block space-y-1.5">
              <span class="text-xs font-black">نام *</span>
              <input v-model="form.name" required class="admin-input w-full">
            </label>
            <label class="block space-y-1.5">
              <span class="text-xs font-black">نام اصلی (لاتین)</span>
              <input v-model="form.original_name" class="admin-input w-full" dir="ltr">
            </label>
            <label class="block space-y-1.5">
              <span class="text-xs font-black">تاریخ تولد</span>
              <input v-model="form.birth_date" type="date" class="admin-input w-full" dir="ltr">
            </label>
            <label class="block space-y-1.5">
              <span class="text-xs font-black">محل تولد</span>
              <input v-model="form.birth_place" class="admin-input w-full">
            </label>
          </div>
          <label class="block space-y-1.5">
            <span class="text-xs font-black">بیوگرافی</span>
            <textarea v-model="form.biography" rows="4" class="admin-input w-full" />
          </label>
          <label class="block space-y-1.5">
            <span class="text-xs font-black">عکس</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" class="admin-input w-full" @change="selectPhoto">
          </label>
        </template>

        <div class="flex justify-end gap-2 border-t border-[var(--admin-border)] pt-4">
          <AdminButton variant="ghost" type="button" @click="modalOpen = false">انصراف</AdminButton>
          <AdminButton type="submit" :loading="saving">ذخیره</AdminButton>
        </div>
      </form>
    </AdminModal>

    <AdminConfirmDialog
      :open="!!deleteTarget"
      title="حذف مورد"
      :message="deleteTarget ? `«${titleFor(deleteTarget)}» حذف شود؟ موارد متصل به فیلم یا سریال قابل حذف نیستند.` : ''"
      confirm-label="حذف"
      dangerous
      :loading="deleting"
      @close="deleteTarget = null"
      @confirm="confirmDelete"
    />
  </div>
</template>
