<script setup lang="ts">
import ArrowRight from '~icons/lucide/arrow-right'
import Check from '~icons/lucide/check'
import ImageIcon from '~icons/lucide/image'
import Refresh from '~icons/lucide/rotate-cw'
import Save from '~icons/lucide/save'
import Shield from '~icons/lucide/shield-check'
import Upload from '~icons/lucide/upload'
import type { AdminEditorOption, AdminFieldSpec } from '~/types/editorSchema'
import type { AdminMovie, AdminSeries } from '~/types'
import { useContentEditor } from '~/composables/useContentEditor'

const props = defineProps<{ contentType: 'movie' | 'series'; itemId?: number }>()

const editor = useContentEditor(
  props.contentType === 'movie' ? createMovieEditorConfig() : createSeriesEditorConfig(),
  props.itemId,
)

const {
  config, itemId, loading, saving, error, fieldErrors, item,
  genres, countries, activeSection,
  posterPreview, backdropPreview, isDirty, pageTitle, form,
  initialize, save, validate, addDownloadLink, removeDownloadLink, derivedAvailability,
  selectImage, prepareSync, syncOpen, syncLoading, syncPreview, syncOverwrite, confirmSync,
  f2mPageUrl, f2mCrawlLoading, crawlFilm2MediaDownloads,
  providerDiscoverLoading, queueProviderDiscover,
  inputClass, textareaClass,
} = editor

function bind(spec: AdminFieldSpec) {
  const value = form[spec.key as keyof typeof form]
  return {
    modelValue: value,
    'onUpdate:modelValue': (next: unknown) => { (form as Record<string, unknown>)[spec.key] = next as never },
  }
}

function fieldError(spec: AdminFieldSpec) {
  return fieldErrors[spec.key] || ''
}

const catalogTypeOptions = [
  { value: 'movie', title: 'فیلم سینمایی' },
  { value: 'documentary', title: 'مستند' },
  { value: 'short', title: 'فیلم کوتاه' },
]
const contentFormatOptions = [
  { value: 'live_action', title: 'لایو اکشن' },
  { value: 'animation', title: 'انیمیشن' },
  { value: 'short', title: 'کوتاه' },
]
const mediaStatusOptions = [
  { value: 'missing', title: 'ناقص' },
  { value: 'processing', title: 'در حال پردازش' },
  { value: 'ready', title: 'آماده' },
  { value: 'failed', title: 'ناموفق' },
]
const seriesStatusOptions = [
  { value: 'ongoing', title: 'در حال پخش' },
  { value: 'ended', title: 'پایان‌یافته' },
  { value: 'upcoming', title: 'به‌زودی' },
  { value: 'cancelled', title: 'لغوشده' },
  { value: 'on_hold', title: 'متوقف' },
]
const publicationOptions = [
  { value: 'draft', title: 'پیش‌نویس', text: 'فقط برای تیم محتوا' },
  { value: 'published', title: 'منتشرشده', text: 'قابل مشاهده در سایت' },
  { value: 'archived', title: 'آرشیوشده', text: 'خارج از نمایش عمومی' },
]

function optionsFor(spec: AdminFieldSpec): AdminEditorOption[] {
  if (spec.options?.length) return spec.options
  if (spec.key === 'catalog_type') return catalogTypeOptions as AdminEditorOption[]
  if (spec.key === 'content_format') return contentFormatOptions as AdminEditorOption[]
  if (spec.key === 'media_status') return mediaStatusOptions as AdminEditorOption[]
  if (spec.key === 'status') return seriesStatusOptions as AdminEditorOption[]
  if (spec.key === 'publication_status') return publicationOptions
  return []
}

const publishedSlug = computed(() => form.slug || (item.value as AdminMovie | AdminSeries | null)?.slug || '')
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-9">
    <header class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div class="min-w-0 flex-1">
        <NuxtLink :to="config.listBackHref" class="admin-focus mb-3 inline-flex min-h-11 items-center gap-1.5 text-xs font-bold text-[var(--admin-accent)] hover:underline">
          <ArrowRight class="size-4" /> بازگشت به {{ config.contentType === 'movie' ? 'فیلم‌ها' : 'سریال‌ها' }}
        </NuxtLink>
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="truncate text-2xl font-black sm:text-3xl">{{ pageTitle }}</h1>
          <AdminBadge v-if="item" :tone="config.contentType === 'movie' ? ((item as AdminMovie).publication_status) : ((item as AdminSeries).is_published ? 'published' : 'draft')">
            {{ config.contentType === 'movie'
              ? ((item as AdminMovie).publication_status === 'published' ? 'منتشرشده' : (item as AdminMovie).publication_status === 'archived' ? 'آرشیوشده' : 'پیش‌نویس')
              : ((item as AdminSeries).is_published ? 'منتشرشده' : 'پیش‌نویس') }}
          </AdminBadge>
          <AdminBadge v-if="item?.tmdb_id" tone="tmdb">متصل به TMDB</AdminBadge>
        </div>
        <p class="mt-2 max-w-2xl text-sm leading-7 text-[var(--admin-muted)]">
          اطلاعات را بخش‌به‌بخش تکمیل کنید؛ تغییرات دستی شما هنگام همگام‌سازی عادی محافظت می‌شوند.
        </p>
      </div>
      <div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
        <AdminButton v-if="config.includes.syncAvailable && item?.tmdb_id" class="w-full shrink-0 sm:w-auto" variant="secondary" :disabled="isDirty" @click="prepareSync">
          <template #icon><Refresh class="size-4" /></template>
          همگام‌سازی TMDB
        </AdminButton>
      </div>
    </header>

    <div v-if="loading" class="mt-6 grid gap-5 lg:grid-cols-[220px_1fr]">
      <div class="hidden h-80 animate-pulse rounded-2xl bg-[var(--admin-surface-muted)] lg:block" />
      <div class="h-[600px] animate-pulse rounded-2xl bg-[var(--admin-surface-muted)]" />
    </div>

    <AdminState v-else-if="error && !item && itemId" class="mt-6" kind="error" title="ویرایشگر بارگذاری نشد" :message="error.message" @retry="initialize" />

    <form v-else class="mt-6 pb-28" @submit.prevent="save">
      <div class="grid items-start gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav class="sticky top-5 hidden max-h-[calc(100dvh-2.5rem)] overflow-y-auto rounded-2xl border border-[var(--admin-border)] bg-[var(--admin-surface)] p-2 lg:block" aria-label="بخش‌های فرم">
          <button v-for="section in config.sections" :key="section.id" type="button" class="admin-focus min-h-11 w-full rounded-xl px-3 py-2.5 text-right text-xs font-extrabold" :class="activeSection === section.id ? 'bg-[var(--admin-primary)] text-white' : 'text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)]'" @click="activeSection = section.id">
            {{ section.label }}
          </button>
          <div v-if="(item as AdminMovie | null)?.manual_override_fields?.length" class="mt-2 border-t border-[var(--admin-border)] p-3">
            <p class="flex items-center gap-1.5 text-[11px] font-bold text-emerald-800">
              <Shield class="size-3.5" /> {{ (item as AdminMovie).manual_override_fields.length.toLocaleString('fa-IR') }} فیلد دستی محافظت‌شده
            </p>
          </div>
        </nav>

        <div class="min-w-0">
          <select v-model="activeSection" class="admin-focus mb-4 h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 text-sm font-bold lg:hidden" aria-label="بخش‌های فرم">
            <option v-for="section in config.sections" :key="section.id" :value="section.id">{{ section.label }}</option>
          </select>

          <UiErrorAlert v-if="error" class="mb-4" :error="error" @close="error = null" />

          <AdminCard v-for="section in config.sections" :key="section.id" v-show="activeSection === section.id" class="p-5 sm:p-7">
            <h2 class="mb-6 text-lg font-black">{{ section.label }}</h2>
            <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              <template v-for="spec in section.fields" :key="spec.key">
                <!-- text / number / url / ids -->
                <AdminField
                  v-if="['text','number','url','tmdb-id','imdb-id','date'].includes(spec.type)"
                  :class="spec.colSpan || (spec.key === 'short_description' || spec.key === 'description' ? 'sm:col-span-2' : '')"
                  :label="spec.label || ''"
                  :required="spec.required"
                  :hint="spec.hint"
                  :error="fieldError(spec)"
                >
                  <input
                    v-bind="bind(spec)"
                    :type="spec.type === 'number' ? 'number' : spec.type === 'date' ? 'date' : 'text'"
                    :dir="spec.dir"
                    :class="inputClass"
                    :placeholder="spec.placeholder"
                  >
                </AdminField>

                <AdminField
                  v-else-if="spec.type === 'textarea'"
                  :class="spec.colSpan || 'sm:col-span-2'"
                  :label="spec.label || ''"
                  :hint="spec.hint"
                  :error="fieldError(spec)"
                >
                  <textarea v-bind="bind(spec)" :rows="spec.key === 'description' ? 7 : 3" :class="textareaClass" />
                </AdminField>

                <!-- select -->
                <AdminField v-else-if="spec.type === 'select'" :class="spec.colSpan || ''" :label="spec.label || ''" :error="fieldError(spec)">
                  <select v-bind="bind(spec)" :class="inputClass">
                    <option v-for="option in optionsFor(spec)" :key="option.value" :value="option.value">{{ option.title }}</option>
                  </select>
                </AdminField>

                <!-- checkbox -->
                <label v-else-if="spec.type === 'checkbox'" :class="['flex items-center gap-2 text-xs font-bold', spec.colSpan || '']">
                  <input v-bind="bind(spec)" type="checkbox" class="size-4 accent-[var(--admin-primary)]">
                  {{ spec.label }}
                </label>

                <!-- radio cards (publication) -->
                <div v-else-if="spec.type === 'radio-cards'" class="sm:col-span-2 lg:col-span-3">
                  <div class="grid gap-3 sm:grid-cols-3">
                    <label
                      v-for="option in optionsFor(spec)"
                      :key="option.value"
                      class="admin-focus cursor-pointer rounded-2xl border p-4 transition-colors"
                      :class="form.publication_status === option.value ? 'border-[var(--admin-primary)] bg-[var(--admin-primary)]/6 shadow-sm' : 'border-[var(--admin-border)] bg-white hover:border-[var(--admin-accent)]/40'"
                    >
                      <input v-model="form.publication_status" type="radio" :value="option.value" class="sr-only">
                      <span class="flex items-center gap-2 text-sm font-black">
                        <Check v-if="form.publication_status === option.value" class="size-4 text-[var(--admin-primary)]" />
                        {{ option.title }}
                      </span>
                      <span v-if="option.text" class="mt-1 block text-xs text-[var(--admin-muted)]">{{ option.text }}</span>
                    </label>
                  </div>
                </div>

                <!-- genres picker -->
                <fieldset v-else-if="spec.type === 'genres-picker'" class="sm:col-span-2 lg:col-span-3">
                  <legend class="mb-2 text-xs font-extrabold">{{ spec.label }}</legend>
                  <div class="flex flex-wrap gap-2">
                    <label v-for="genre in genres" :key="genre.id" class="admin-focus inline-flex min-h-10 cursor-pointer items-center rounded-xl border px-3 py-2 text-xs font-bold" :class="form.genre_ids.includes(genre.id) ? 'border-[var(--admin-primary)] bg-[var(--admin-primary)] text-white' : 'border-[var(--admin-border)] bg-white text-[var(--admin-muted)]'">
                      <input v-model="form.genre_ids" type="checkbox" :value="genre.id" class="sr-only">
                      {{ genre.title }}
                    </label>
                  </div>
                </fieldset>

                <!-- countries picker (movies) -->
                <fieldset v-else-if="spec.type === 'countries-picker'" class="sm:col-span-2 lg:col-span-3">
                  <legend class="mb-2 text-xs font-extrabold">{{ spec.label }}</legend>
                  <div v-if="countries.length" class="flex flex-wrap gap-2">
                    <label v-for="country in countries" :key="country.id" class="admin-focus inline-flex min-h-10 cursor-pointer items-center rounded-xl border px-3 py-2 text-xs font-bold" :class="form.country_ids.includes(country.id) ? 'border-[var(--admin-primary)] bg-[var(--admin-primary)] text-white' : 'border-[var(--admin-border)] bg-white text-[var(--admin-muted)]'">
                      <input v-model="form.country_ids" type="checkbox" :value="country.id" class="sr-only">
                      {{ country.name }}<span v-if="country.code" class="ms-1 opacity-70" dir="ltr">({{ country.code }})</span>
                    </label>
                  </div>
                  <p v-else class="rounded-xl border border-dashed border-[var(--admin-border)] bg-[var(--admin-surface-muted)]/40 px-4 py-4 text-xs leading-6 text-[var(--admin-muted)]">هنوز کشوری در کاتالوگ نیست. با همگام‌سازی TMDB کشورها اضافه می‌شوند.</p>
                </fieldset>

                <!-- availability indicators -->
                <div v-else-if="spec.type === 'availability-indicators'" class="flex flex-wrap gap-4 sm:col-span-2 lg:col-span-3">
                  <span class="inline-flex items-center gap-2 rounded-xl border border-[var(--admin-border)] bg-[var(--admin-surface-muted)]/50 px-3 py-2 text-xs font-bold" :class="form.is_dubbed ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'text-[var(--admin-muted)]'">
                    <span class="size-2 rounded-full" :class="form.is_dubbed ? 'bg-emerald-500' : 'bg-[var(--admin-border)]'" />
                    {{ form.is_dubbed ? 'دوبله از لینک‌های دانلود تشخیص داده شد' : 'دوبله ندارد (بر اساس لینک‌ها)' }}
                  </span>
                  <span class="inline-flex items-center gap-2 rounded-xl border border-[var(--admin-border)] bg-[var(--admin-surface-muted)]/50 px-3 py-2 text-xs font-bold" :class="form.has_subtitle ? 'border-sky-300 bg-sky-50 text-sky-800' : 'text-[var(--admin-muted)]'">
                    <span class="size-2 rounded-full" :class="form.has_subtitle ? 'bg-sky-500' : 'bg-[var(--admin-border)]'" />
                    {{ form.has_subtitle ? 'زیرنویس از لینک‌های دانلود تشخیص داده شد' : 'زیرنویس ندارد (بر اساس لینک‌ها)' }}
                  </span>
                </div>

                <!-- image upload -->
                <template v-else-if="spec.type === 'image-upload'">
                  <div>
                    <p class="mb-2 text-xs font-extrabold">{{ spec.label }}</p>
                    <label class="admin-focus flex min-h-52 cursor-pointer items-center justify-center overflow-hidden rounded-2xl border border-dashed border-[var(--admin-accent)]/45 bg-[var(--admin-surface-muted)]/45">
                      <img v-if="spec.kind === 'poster' ? posterPreview : backdropPreview" :src="spec.kind === 'poster' ? posterPreview : backdropPreview" alt="پیش‌نمایش" class="h-full min-h-52 w-full object-cover">
                      <span v-else class="text-center text-xs text-[var(--admin-muted)]">
                        <Upload class="mx-auto mb-2 size-5 text-[var(--admin-primary)]" />
                        <strong class="block text-sm text-[var(--admin-text)]">{{ spec.kind === 'poster' ? 'انتخاب پوستر' : 'انتخاب تصویر افقی' }}</strong>
                      </span>
                      <input type="file" accept="image/jpeg,image/png,image/webp" class="sr-only" @change="selectImage($event, spec.kind as 'poster' | 'backdrop')">
                    </label>
                  </div>
                </template>

                <!-- download links editor -->
                <div v-else-if="spec.type === 'download-links'" class="mt-4 sm:col-span-2 lg:col-span-3 rounded-2xl border border-[var(--admin-border)] bg-[var(--admin-surface-muted)]/40 p-4 sm:p-5">
                  <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h3 class="text-sm font-black">لینک‌های دانلود</h3>
                      <p class="mt-1 text-xs leading-6 text-[var(--admin-muted)]">نوع نسخه را مشخص کنید تا نشان‌های سایت عمومی درست باشد. اگر لینک SoftSub یا دوبله باشد، پرچم‌های «زیرنویس» و «دوبله» خودکار فعال می‌شوند.</p>
                    </div>
                    <AdminButton type="button" size="sm" variant="secondary" @click="addDownloadLink">افزودن کیفیت</AdminButton>
                  </div>
                  <div v-if="form.download_links.length" class="mt-4 space-y-3">
                    <div v-for="(link, index) in form.download_links" :key="index" class="grid gap-3 rounded-xl border border-[var(--admin-border)] bg-white p-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_1.2fr_minmax(0,1.4fr)_auto]">
                      <AdminField label="برچسب"><input v-model="link.label" :class="inputClass" placeholder="دانلود ۱۰۸۰"></AdminField>
                      <AdminField label="کیفیت"><input v-model="link.quality" :class="inputClass" placeholder="1080p"></AdminField>
                      <AdminField label="حجم"><input v-model="link.size_label" :class="inputClass" placeholder="۲.۱ GB"></AdminField>
                      <AdminField label="نوع نسخه">
                        <select v-model="link.kind" :class="inputClass">
                          <option value="">خودکار از برچسب</option>
                          <option value="dubbed">دوبله فارسی</option>
                          <option value="softsub">زیرنویس نرم (SoftSub)</option>
                          <option value="hardsub">زیرنویس چسبیده (HardSub)</option>
                          <option value="other">سایر</option>
                        </select>
                      </AdminField>
                      <AdminField label="لینک"><input v-model="link.url" dir="ltr" :class="inputClass" placeholder="https://example.com/file-1080p.mp4"></AdminField>
                      <div class="flex items-end">
                        <button type="button" class="admin-focus inline-flex min-h-11 items-center rounded-xl px-3 text-xs font-bold text-[var(--admin-danger)] hover:bg-red-50" @click="removeDownloadLink(index)">حذف</button>
                      </div>
                    </div>
                  </div>
                  <p v-else class="mt-4 text-xs text-[var(--admin-muted)]">هنوز لینک دانلودی ثبت نشده است.</p>
                </div>

                <!-- Film2Media crawl -->
                <div v-else-if="spec.type === 'f2m-crawl' && itemId" class="sm:col-span-2 lg:col-span-3 rounded-2xl border border-[var(--admin-border)] bg-white p-4">
                  <h3 class="text-sm font-black">همگام‌سازی Film2Media (myf2m)</h3>
                  <p class="mt-1 text-xs text-[var(--admin-muted)]">آدرس صفحه در myf2m را بگذارید تا لینک‌های دانلود و فلگ‌های دوبله/زیرنویس پر شوند. اگر خالی باشد سرور از عنوان/سال جستجو می‌کند.</p>
                  <div class="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                    <AdminField label="آدرس صفحه Film2Media" hint="مثال: https://www.myf2m.info/movies/slug/">
                      <input v-model="f2mPageUrl" dir="ltr" :class="inputClass" placeholder="https://www.myf2m.info/movies/...">
                    </AdminField>
                    <div class="flex items-end">
                      <AdminButton type="button" :loading="f2mCrawlLoading" :disabled="isDirty || f2mCrawlLoading" @click="crawlFilm2MediaDownloads">
                        <template #icon><Refresh class="size-3.5" :class="f2mCrawlLoading && 'animate-spin'" /></template>
                        {{ f2mCrawlLoading ? 'در حال خزیدن…' : 'دریافت لینک‌ها' }}
                      </AdminButton>
                    </div>
                  </div>
                  <p v-if="isDirty" class="mt-3 text-xs text-amber-800">قبل از برداشت لینک، تغییرات را ذخیره کنید.</p>
                  <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--admin-border)] pt-3">
                    <AdminButton type="button" variant="secondary" size="sm" :loading="providerDiscoverLoading" :disabled="providerDiscoverLoading" @click="queueProviderDiscover">
                      کاوش ارائه‌دهنده‌ها (واچ‌پارتی/دانلود)
                    </AdminButton>
                    <span class="text-[11px] leading-5 text-[var(--admin-muted)]">یک جوی کاوش در صف می‌گذارد؛ نتیجه در «ارائه‌دهنده مجاز» قابل تأیید است.</span>
                  </div>
                </div>

                <!-- TMDB sync -->
                <div v-else-if="spec.type === 'sync-tmdb'" class="sm:col-span-2 lg:col-span-3">
                  <AdminButton v-if="config.includes.syncAvailable && item?.tmdb_id" size="sm" variant="secondary" :disabled="isDirty" @click="prepareSync">
                    <template #icon><Refresh class="size-3.5" /></template>
                    بررسی همگام‌سازی
                  </AdminButton>
                  <div v-if="item?.last_tmdb_sync_at" class="mt-4 rounded-xl bg-teal-50 p-3 text-xs text-teal-800">آخرین همگام‌سازی: {{ new Date(item.last_tmdb_sync_at).toLocaleString('fa-IR') }}</div>
                </div>

                <!-- crew display -->
                <div v-else-if="spec.type === 'crew-display'" class="sm:col-span-2 lg:col-span-3">
                  <div v-if="(item as AdminMovie)?.directors?.length" class="mt-6">
                    <h3 class="text-sm font-black">کارگردان</h3>
                    <div class="mt-3 flex flex-wrap gap-2">
                      <span v-for="person in (item as AdminMovie).directors" :key="person.id" class="rounded-xl border border-[var(--admin-border)] bg-white px-3 py-2 text-xs font-bold">{{ person.name }}</span>
                    </div>
                  </div>
                  <div class="mt-6">
                    <h3 class="text-sm font-black">{{ config.contentType === 'movie' ? 'بازیگران' : 'بازیگران سریال' }}</h3>
                    <div v-if="((item as AdminMovie)?.movie_actors?.length || (item as AdminSeries)?.series_actors?.length)" class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                      <article v-for="credit in (item as AdminMovie).movie_actors || (item as AdminSeries).series_actors" :key="credit.id" class="overflow-hidden rounded-xl border border-[var(--admin-border)] bg-white">
                        <div class="aspect-[3/4] bg-[var(--admin-surface-muted)]">
                          <img v-if="credit.actor.photo || credit.actor.photo_external_url" :src="credit.actor.photo || credit.actor.photo_external_url || ''" :alt="credit.actor.name" class="h-full w-full object-cover" loading="lazy">
                          <div v-else class="grid h-full place-items-center text-2xl font-black text-[var(--admin-muted)]">{{ credit.actor.name.slice(0, 1) }}</div>
                        </div>
                        <div class="p-2.5">
                          <p class="truncate text-xs font-black">{{ credit.actor.name }}</p>
                          <p class="mt-0.5 truncate text-[11px] text-[var(--admin-muted)]">{{ credit.role || 'بازیگر' }}</p>
                        </div>
                      </article>
                    </div>
                    <p v-else class="mt-3 rounded-xl border border-dashed border-[var(--admin-border)] bg-[var(--admin-surface-muted)]/40 px-4 py-5 text-xs leading-6 text-[var(--admin-muted)]">
                      بازیگری ثبت نشده. پس از اتصال TMDB، «همگام‌سازی TMDB» را بزنید تا بازیگران اینجا و در صفحه عمومی نمایش داده شوند.
                    </p>
                  </div>
                  <div v-if="(item as AdminMovie).crew_metadata?.length" class="mt-6">
                    <h3 class="text-sm font-black">عوامل منتخب</h3>
                    <div class="mt-3 grid gap-2 sm:grid-cols-2">
                      <div v-for="person in (item as AdminMovie).crew_metadata.slice(0, 12)" :key="`${person.tmdb_id}-${person.job}`" class="rounded-xl border border-[var(--admin-border)] bg-white p-3">
                        <p class="text-sm font-bold">{{ person.name }}</p>
                        <p class="mt-0.5 text-[11px] text-[var(--admin-muted)]">{{ person.job }} · {{ person.department }}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- published url -->
                <div v-else-if="spec.type === 'published-url' && publishedSlug && (config.contentType === 'movie' ? form.publication_status === 'published' : form.is_published)" class="sm:col-span-2 lg:col-span-3 flex flex-col gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p class="text-sm font-black text-emerald-950">همگام با سایت عمومی</p>
                    <p class="mt-1 text-xs leading-6 text-emerald-900">لینک‌های دانلود، بازیگران، کشورها و وضعیت انتشار دقیقاً همان چیزی است که کاربر در صفحه {{ config.contentNoun }} می‌بیند.</p>
                  </div>
                  <NuxtLink :to="`${config.contentType === 'movie' ? '/movies' : '/series'}/${publishedSlug}`" target="_blank" class="admin-focus inline-flex min-h-11 shrink-0 items-center justify-center rounded-xl bg-emerald-700 px-4 text-xs font-bold text-white hover:bg-emerald-800">
                    مشاهده در سایت
                  </NuxtLink>
                </div>
              </template>
            </div>
          </AdminCard>
        </div>
      </div>

      <div class="sticky bottom-3 z-20 mt-5 flex flex-col gap-3 rounded-2xl border border-[var(--admin-border)] bg-white/95 p-3 shadow-[0_16px_50px_rgb(var(--admin-primary-rgb)/16%)] backdrop-blur sm:flex-row sm:items-center sm:gap-4 sm:px-4">
        <div class="min-w-0 flex-1">
          <p class="text-xs font-extrabold" :class="isDirty ? 'text-amber-800' : 'text-emerald-800'">{{ isDirty ? 'تغییرات ذخیره‌نشده دارید' : 'همه تغییرات ذخیره شده‌اند' }}</p>
          <p class="mt-0.5 text-[11px] text-[var(--admin-muted)]">
            {{ config.contentType === 'movie'
              ? (form.publication_status === 'published' ? 'پس از ذخیره، این فیلم در سایت دیده می‌شود.' : form.publication_status === 'archived' ? 'این فیلم در آرشیو است و در سایت دیده نمی‌شود.' : 'این فیلم هنوز پیش‌نویس است.')
              : (form.is_published ? 'پس از ذخیره، این سریال در سایت دیده می‌شود.' : 'این سریال هنوز منتشر نشده است.') }}
          </p>
        </div>
        <AdminButton type="submit" :loading="saving" :disabled="!isDirty">
          <template #icon><Save class="size-4" /></template>
          {{ config.contentType === 'movie' && form.publication_status === 'published' && isDirty ? 'ذخیره و انتشار' : 'ذخیره تغییرات' }}
        </AdminButton>
      </div>
    </form>

    <AdminModal :open="syncOpen" title="همگام‌سازی امن TMDB" description="ابتدا پیش‌نمایش بدون تغییر پایگاه داده آماده شده است." size="sm" :closeable="!syncLoading" @close="syncOpen = false">
      <div class="p-6">
        <div v-if="syncLoading && !syncPreview" class="py-8 text-center text-sm text-[var(--admin-muted)]">در حال مقایسه اطلاعات…</div>
        <template v-else>
          <div class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs leading-6 text-emerald-900">
            <strong class="block text-sm">ویرایش‌های دستی محافظت می‌شوند</strong>
            {{ (syncPreview?.skipped_manual_fields.length || 0).toLocaleString('fa-IR') }} فیلد در حالت عادی دست‌نخورده باقی می‌ماند.
          </div>
          <label class="mt-4 flex cursor-pointer gap-3 rounded-2xl border border-red-200 bg-red-50 p-4">
            <input v-model="syncOverwrite" type="checkbox" class="mt-1 accent-[var(--admin-danger)]">
            <span class="text-xs leading-6 text-[var(--admin-danger)]">
              <strong class="block text-sm">بازنویسی اطلاعات دستی</strong>
              تنها وقتی فعال کنید که داده TMDB باید جایگزین اصلاحات تیم شود.
            </span>
          </label>
        </template>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <AdminButton variant="ghost" :disabled="syncLoading" @click="syncOpen = false">انصراف</AdminButton>
          <AdminButton :loading="syncLoading" @click="confirmSync">تأیید همگام‌سازی</AdminButton>
        </div>
      </template>
    </AdminModal>
  </div>
</template>