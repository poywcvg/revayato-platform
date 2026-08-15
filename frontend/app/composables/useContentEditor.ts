import type { AdminEditorConfig, AdminItemApiLike } from '~/types/editorSchema'
import type {
  AdminCountry,
  AdminGenre,
  AdminMovie,
  AdminSeries,
  AppErrorDetails,
  TMDBImportResponse,
} from '~/types'

/** Normalised form model shared by movies and series. */
export interface ContentForm {
  title: string
  original_title: string
  slug: string
  short_description: string
  description: string
  publication_status: 'draft' | 'published' | 'archived'
  is_published: boolean
  status: string
  release_date: string
  release_year: string
  start_year: string
  end_year: string
  duration_minutes: string
  age_rating: string
  language: string
  original_language: string
  spoken_languages: string
  genre_ids: number[]
  country_ids: number[]
  poster_external_url: string
  backdrop_external_url: string
  trailer_external_url: string
  trailer_url: string
  video_url: string
  download_key: string
  quality: string
  tmdb_id: string
  imdb_id: string
  imdb_rating: string
  content_format: 'live_action' | 'animation' | 'short'
  is_dubbed: boolean
  has_subtitle: boolean
  is_uncensored: boolean
  is_featured: boolean
  is_recommended: boolean
  media_status: string
  meta_title: string
  meta_description: string
  seo_keywords: string
  catalog_type: 'movie' | 'documentary' | 'short'
  download_links: Array<{
    label: string
    url: string
    quality: string
    size_label: string
    kind: string
    subtitle_type: string
  }>
}

export function emptyForm(): ContentForm {
  return {
    title: '', original_title: '', slug: '', short_description: '', description: '',
    publication_status: 'draft', is_published: false, status: 'ongoing',
    release_date: '', release_year: '', start_year: '', end_year: '',
    duration_minutes: '', age_rating: '', language: '', original_language: '',
    spoken_languages: '', genre_ids: [], country_ids: [],
    poster_external_url: '', backdrop_external_url: '', trailer_external_url: '',
    trailer_url: '', video_url: '', download_key: '', quality: '',
    tmdb_id: '', imdb_id: '', imdb_rating: '',
    content_format: 'live_action', is_dubbed: false, has_subtitle: false,
    is_uncensored: false, is_featured: false, is_recommended: false,
    media_status: 'missing', meta_title: '', meta_description: '', seo_keywords: '',
    catalog_type: 'movie',
    download_links: [],
  }
}

function stringList(value: string) {
  return value.split(/[،,]/).map(item => item.trim()).filter(Boolean)
}

function normalizeDownloadLinks(value: AdminMovie | AdminSeries) {
  const links = (value as AdminMovie).download_links?.length
    ? (value as AdminMovie).download_links
    : ((value as AdminMovie).download_key
      ? [{ label: '', url: (value as AdminMovie).download_key, quality: (value as AdminMovie).quality || '', size_label: '', kind: '', subtitle_type: '' }]
      : [])
  return links.map(link => ({
    label: link.label || link.quality || 'دانلود',
    url: link.url || link.key || '',
    quality: link.quality || '',
    size_label: link.size_label || '',
    kind: link.kind || '',
    subtitle_type: link.subtitle_type || '',
  }))
}

/**
 * The shared content-editor engine. Drives the form state, dirty-tracking,
 * API payload building, validation, image handling, download links, TMDB sync
 * and the Film2Media crawler for BOTH movies and series.
 */
export function useContentEditor(config: AdminEditorConfig, itemId?: number) {
  const api = config.api()
  const notifications = useNotifications()
  const router = useRouter()

  const loading = ref(Boolean(itemId))
  const saving = ref(false)
  const error = ref<AppErrorDetails | null>(null)
  const fieldErrors = reactive<Record<string, string>>({})
  const item = ref<AdminMovie | AdminSeries | null>(null)
  const genres = ref<AdminGenre[]>([])
  const countries = ref<AdminCountry[]>([])
  const activeSection = ref(config.sections[0]?.id || 'basic')
  const posterFile = ref<File | null>(null)
  const backdropFile = ref<File | null>(null)
  const posterPreview = ref('')
  const backdropPreview = ref('')
  const initialSnapshot = ref('')

  const syncOpen = ref(false)
  const syncLoading = ref(false)
  const syncPreview = ref<TMDBImportResponse | null>(null)
  const syncOverwrite = ref(false)

  const f2mPageUrl = ref('')
  const f2mCrawlLoading = ref(false)
  const forceDirty = ref(false)

  const form = reactive<ContentForm>(emptyForm())

  const inputClass = 'admin-focus min-h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3.5 text-sm outline-none placeholder:text-[var(--admin-muted)]/60 focus:border-[var(--admin-accent)]'
  const textareaClass = `${inputClass} resize-y py-3 leading-7`
  const isDirty = computed(() => forceDirty.value || (Boolean(initialSnapshot.value) && snapshot() !== initialSnapshot.value))
  const pageTitle = computed(() => itemId ? (form.title || config.editTitle) : config.newTitle)

  function snapshot() {
    return JSON.stringify({ ...form, poster: posterFile.value?.name || '', backdrop: backdropFile.value?.name || '' })
  }

  function fillForm(value: AdminMovie | AdminSeries) {
    const movie = value as AdminMovie
    Object.assign(form, emptyForm(), {
      title: value.title || '',
      original_title: value.original_title || '',
      slug: value.slug || '',
      short_description: value.short_description || '',
      description: value.description || '',
      publication_status: movie.publication_status || 'draft',
      is_published: (value as AdminSeries).is_published ?? false,
      status: (value as AdminSeries).status || 'ongoing',
      release_date: movie.release_date || '',
      release_year: movie.release_year ? String(movie.release_year) : '',
      start_year: (value as AdminSeries).start_year ? String((value as AdminSeries).start_year) : '',
      end_year: (value as AdminSeries).end_year ? String((value as AdminSeries).end_year) : '',
      duration_minutes: movie.duration_minutes ? String(movie.duration_minutes) : '',
      age_rating: value.age_rating || '',
      language: value.original_language || value.language || '',
      original_language: value.original_language || value.language || '',
      spoken_languages: (movie.spoken_languages || []).map(sl => sl.name || sl.english_name || sl.iso_639_1 || '').filter(Boolean).join('، '),
      genre_ids: value.genre_ids || [],
      country_ids: value.country_ids || [],
      poster_external_url: value.poster_external_url || '',
      backdrop_external_url: value.backdrop_external_url || '',
      trailer_external_url: value.trailer_external_url || '',
      trailer_url: value.trailer_url || '',
      video_url: movie.video_url || '',
      download_key: movie.download_key || '',
      quality: movie.quality || '',
      tmdb_id: value.tmdb_id ? String(value.tmdb_id) : '',
      imdb_id: value.imdb_id || '',
      imdb_rating: value.imdb_rating != null && value.imdb_rating !== '' ? String(value.imdb_rating) : '',
      content_format: value.content_format || 'live_action',
      is_dubbed: value.is_dubbed,
      has_subtitle: value.has_subtitle,
      is_uncensored: value.is_uncensored,
      is_featured: value.is_featured,
      is_recommended: (movie.is_recommended ?? false),
      media_status: movie.media_status || 'missing',
      catalog_type: movie.catalog_type || 'movie',
      meta_title: movie.meta_title || '',
      meta_description: movie.meta_description || '',
      seo_keywords: (movie.seo_keywords || []).join('، '),
      download_links: normalizeDownloadLinks(value),
    })
    posterPreview.value = value.poster_url || ''
    backdropPreview.value = value.backdrop_url || ''
  }

  async function initialize() {
    loading.value = true
    error.value = null
    try {
      const requests: [
        Promise<AdminGenre[]>,
        Promise<AdminCountry[]>,
        Promise<AdminMovie | AdminSeries> | null,
      ] = [
        api.genres(),
        api.countries(),
        itemId ? api.detail(itemId) : null,
      ]
      const [genreList, countryList, detail] = await Promise.all([
        requests[0],
        requests[1],
        requests[2] || Promise.resolve(null),
      ])
      genres.value = genreList
      countries.value = countryList
      if (detail) {
        item.value = detail
        fillForm(detail)
      }
      await nextTick()
      initialSnapshot.value = snapshot()
    } catch (cause) {
      error.value = getAppError(cause, itemId ? 'اطلاعات ویرایشگر دریافت نشد.' : 'برگه آمادهسازی دریافت نشد.')
    } finally {
      loading.value = false
    }
  }

  function validate() {
    Object.keys(fieldErrors).forEach(key => { fieldErrors[key] = '' })
    if (!form.title.trim()) fieldErrors.title = config.contentType === 'movie' ? 'عنوان فیلم الزامی است.' : 'عنوان سریال الزامی است.'
    if (form.imdb_id && !/^tt\d{7,10}$/.test(form.imdb_id)) fieldErrors.imdb_id = 'شناسه IMDb باید مانند tt1234567 باشد.'
    if (config.includes.duration && form.duration_minutes && Number(form.duration_minutes) <= 0) {
      fieldErrors.duration_minutes = 'مدت باید بیشتر از صفر باشد.'
    }
    if (form.meta_description.length > 500) fieldErrors.meta_description = 'توضیح سئو نباید بیشتر از ۵۰۰ نویسه باشد.'
    return !Object.values(fieldErrors).some(Boolean)
  }

  function addDownloadLink() {
    form.download_links.push({ label: 'دانلود', url: '', quality: '', size_label: '', kind: '', subtitle_type: '' })
  }

  function removeDownloadLink(index: number) {
    form.download_links.splice(index, 1)
  }

  const derivedAvailability = computed(() => {
    const links = form.download_links.filter(link => link.url.trim())
    const blob = (link: typeof links[number]) => `${link.kind} ${link.label} ${link.subtitle_type} ${link.url}`.toLowerCase()
    const isDub = links.some((link) => {
      const kind = link.kind.toLowerCase()
      if (['dubbed', 'dub', 'persian_dub', 'farsi_dub'].includes(kind)) return true
      return /(dubbed|\bdub\b|دوبله|persian dub|farsi dub)/.test(blob(link))
    })
    const isSub = links.some((link) => {
      const kind = link.kind.toLowerCase()
      const subtitleType = link.subtitle_type.toLowerCase()
      if (['softsub', 'hardsub', 'subtitle', 'sub'].includes(kind)) return true
      if (subtitleType.includes('soft') || subtitleType.includes('hard')) return true
      return /(softsub|hardsub|زیرنویس|هاردساب|سافت\s*ساب)/.test(blob(link))
    })
    return { is_dubbed: isDub, has_subtitle: isSub }
  })

  watch(derivedAvailability, (value) => {
    form.is_dubbed = value.is_dubbed
    form.has_subtitle = value.has_subtitle
  }, { immediate: true })

  function buildPayload(): FormData | Record<string, unknown> {
    const links = form.download_links
      .map(link => ({
        label: link.label.trim() || link.quality.trim() || 'دانلود',
        url: link.url.trim(),
        quality: link.quality.trim(),
        size_label: link.size_label.trim(),
        ...(link.kind ? { kind: link.kind } : {}),
        ...(link.subtitle_type ? { subtitle_type: link.subtitle_type } : {}),
      }))
      .filter(link => link.url)

    const payload: Record<string, unknown> = {
      title: form.title.trim(),
      original_title: form.original_title.trim(),
      slug: form.slug.trim(),
      short_description: form.short_description.trim(),
      description: form.description.trim(),
      age_rating: form.age_rating.trim(),
      language: form.language.trim(),
      original_language: form.language.trim(),
      poster_external_url: form.poster_external_url.trim(),
      backdrop_external_url: form.backdrop_external_url.trim(),
      trailer_external_url: form.trailer_external_url.trim(),
      trailer_url: form.trailer_url.trim(),
      download_links: links,
      tmdb_id: form.tmdb_id ? Number(form.tmdb_id) : null,
      imdb_id: form.imdb_id.trim() || null,
      imdb_rating: form.imdb_rating !== '' ? Number(form.imdb_rating) : null,
      content_format: form.content_format,
      is_dubbed: form.is_dubbed,
      has_subtitle: form.has_subtitle,
      is_uncensored: form.is_uncensored,
      is_featured: form.is_featured,
      genre_ids: [...form.genre_ids],
      country_ids: [...form.country_ids],
    }

    if (config.contentType === 'movie') {
      const moviePayload = payload as Record<string, unknown>
      const primaryQuality = form.quality.trim() || links[0]?.quality || ''
      const firstUrl = links[0]?.url || ''
      const isExternal = /^https?:\/\//i.test(firstUrl)
      const primaryKey = form.download_key.trim() || (isExternal ? '' : firstUrl)
      Object.assign(moviePayload, {
        release_date: form.release_date || null,
        release_year: form.release_year ? Number(form.release_year) : null,
        duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : null,
        spoken_languages: stringList(form.spoken_languages).map(name => ({ name })),
        video_url: form.video_url.trim(),
        download_key: primaryKey,
        quality: primaryQuality,
        is_recommended: form.is_recommended,
        media_status: form.media_status,
        catalog_type: form.catalog_type,
        meta_title: form.meta_title.trim(),
        meta_description: form.meta_description.trim(),
        seo_keywords: stringList(form.seo_keywords),
        publication_status: form.publication_status,
      })
    } else {
      const seriesPayload = payload as Record<string, unknown>
      Object.assign(seriesPayload, {
        start_year: form.start_year ? Number(form.start_year) : null,
        end_year: form.end_year ? Number(form.end_year) : null,
        status: form.status,
        is_published: form.is_published,
      })
    }

    if (!posterFile.value && !backdropFile.value) {
      return { ...payload, ...(form.genre_ids.length ? {} : { clear_genres: true }), ...(form.country_ids.length ? {} : { clear_countries: true }) }
    }

    const data = new FormData()
    Object.entries(payload).forEach(([key, value]) => {
      if (key === 'genre_ids' || key === 'country_ids') return
      if (value === null || value === undefined) data.append(key, '')
      else if (typeof value === 'object') data.append(key, JSON.stringify(value))
      else data.append(key, String(value))
    })
    if (form.genre_ids.length) form.genre_ids.forEach(id => data.append('genre_ids', String(id)))
    else data.append('clear_genres', 'true')
    if (form.country_ids.length) form.country_ids.forEach(id => data.append('country_ids', String(id)))
    else data.append('clear_countries', 'true')
    if (posterFile.value) data.append('poster', posterFile.value)
    if (backdropFile.value) data.append('backdrop', backdropFile.value)
    return data
  }

  /** After a successful save: reset dirty state and follow-up actions. */
  function afterSave(saved: AdminMovie | AdminSeries) {
    item.value = saved
    fillForm(saved)
    posterFile.value = null
    backdropFile.value = null
    forceDirty.value = false
    return nextTick().then(() => { initialSnapshot.value = snapshot() })
  }

  async function save() {
    if (!validate()) {
      notifications.warning('فرم نیاز به بررسی دارد', 'فیلدهای مشخص‌شده را اصلاح کنید.')
      activeSection.value = 'basic'
      return
    }
    saving.value = true
    error.value = null
    try {
      const saved = itemId
        ? await api.update(itemId, buildPayload())
        : await api.create(buildPayload())
      await afterSave(saved)
      const published = config.contentType === 'movie'
        ? (saved as AdminMovie).publication_status === 'published'
        : (saved as AdminSeries).is_published
      const missingDownloads = !(saved.download_links || []).some(link => link?.url || link?.key)
      notifications.success(
        'تغییرات ذخیره شد',
        published
          ? (missingDownloads
            ? `خزنده Film2Media (myf2m) در پس‌زمینه صفحه را پیدا می‌کند و لینک‌های دانلود/پخش ${config.contentNoun} را می‌گذارد.`
            : `نسخه منتشرشده همین حالا با صفحه عمومی ${config.contentNoun} هماهنگ شد.`)
          : (itemId ? `اطلاعات ${config.contentNoun} با موفقیت به‌روزرسانی شد.` : `${config.contentNoun} به‌صورت امن در کاتالوگ ثبت شد.`),
      )
      if (!itemId) await router.replace(`${config.listBackHref}/${saved.id}/edit`)
      if (published && missingDownloads && config.includes.syncAvailable && saved.id) {
        void pollForAutoDownloadLinks(saved.id)
      }
    } catch (cause) {
      error.value = notifications.notifyError(cause, config.contentType === 'movie' ? 'ذخیره تغییرات انجام نشد.' : 'ذخیره سریال انجام نشد.')
    } finally {
      saving.value = false
    }
  }

  let downloadPoll: ReturnType<typeof setInterval> | undefined

  async function pollForAutoDownloadLinks(id: number) {
    if (downloadPoll) clearInterval(downloadPoll)
    let attempts = 0
    downloadPoll = setInterval(async () => {
      attempts += 1
      try {
        const refreshed = await api.detail(id)
        const links = refreshed.download_links || []
        if (links.some(link => link?.url || link?.key)) {
          await afterSave(refreshed)
          notifications.success(
            'لینک‌های دانلود اضافه شد',
            `${links.length.toLocaleString('fa-IR')} لینک از Film2Media (myf2m) ذخیره شد.`,
          )
          activeSection.value = 'media'
          api.bumpPublicCatalog()
          if (downloadPoll) clearInterval(downloadPoll)
          downloadPoll = undefined
        }
      } catch {
        // keep polling until timeout
      }
      if (attempts >= 24 && downloadPoll) {
        clearInterval(downloadPoll)
        downloadPoll = undefined
      }
    }, 5000)
  }

  function selectImage(event: Event, kind: 'poster' | 'backdrop') {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (!file) return
    if (file.size > 8 * 1024 * 1024) {
      notifications.warning('فایل بیش از حد بزرگ است', 'حجم تصویر باید کمتر از ۸ مگابایت باشد.')
      return
    }
    const url = URL.createObjectURL(file)
    if (kind === 'poster') {
      posterFile.value = file
      posterPreview.value = url
    } else {
      backdropFile.value = file
      backdropPreview.value = url
    }
  }

  async function prepareSync() {
    if (!itemId || !form.tmdb_id || !api.sync) return
    syncOpen.value = true
    syncLoading.value = true
    syncPreview.value = null
    try {
      syncPreview.value = await api.sync(itemId, { dry_run: true })
    } catch (cause) {
      notifications.notifyError(cause, 'بررسی TMDB انجام نشد')
      syncOpen.value = false
    } finally {
      syncLoading.value = false
    }
  }

  async function confirmSync() {
    if (!itemId || !api.sync) return
    syncLoading.value = true
    try {
      await api.sync(itemId, { overwrite_manual: syncOverwrite.value })
      notifications.success('اطلاعات همگام شد', 'نسخه تازه TMDB دریافت شد.')
      syncOpen.value = false
      await initialize()
    } catch (cause) {
      notifications.notifyError(cause, 'همگام‌سازی انجام نشد')
    } finally {
      syncLoading.value = false
    }
  }

  async function crawlFilm2MediaDownloads() {
    if (!itemId) {
      notifications.warning('ابتدا ذخیره کنید', `پس از ثبت ${config.contentNoun} می‌توانید لینک‌های Film2Media را بگیرید.`)
      return
    }
    if (isDirty.value) {
      notifications.warning('ابتدا تغییرات را ذخیره کنید', 'برداشت لینک روی نسخه ذخیره‌شده انجام می‌شود.')
      return
    }
    f2mCrawlLoading.value = true
    try {
      const result = await api.crawlProviderDownloads(itemId, {
        page_url: f2mPageUrl.value.trim() || undefined,
        replace: true,
      })
      await afterSave((result.movie || result.series)!)
      api.bumpPublicCatalog()
      notifications.success(
        'لینک‌های دانلود برداشت شد',
        `${result.imported_count.toLocaleString('fa-IR')} لینک از Film2Media (myf2m) به ${config.contentNoun} اضافه شد.`,
      )
      activeSection.value = 'media'
    } catch (cause) {
      notifications.notifyError(cause, 'برداشت لینک انجام نشد')
    } finally {
      f2mCrawlLoading.value = false
    }
  }

  function beforeUnloadHandler(event: BeforeUnloadEvent) {
    if (isDirty.value) event.preventDefault()
  }

  onMounted(() => window.addEventListener('beforeunload', beforeUnloadHandler))
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', beforeUnloadHandler)
    if (downloadPoll) clearInterval(downloadPoll)
  })
  onBeforeRouteLeave(() => {
    if (isDirty.value && import.meta.client && !window.confirm('تغییرات ذخیره‌نشده دارید. بدون ذخیره از صفحه خارج می‌شوید؟')) return false
  })

  return {
    config,
    itemId,
    loading, saving, error, fieldErrors, item,
    genres, countries, activeSection,
    posterFile, backdropFile, posterPreview, backdropPreview,
    isDirty, pageTitle, form,
    snapshot, fillForm, initialize, validate,
    addDownloadLink, removeDownloadLink, derivedAvailability,
    buildPayload, save, selectImage,
    syncOpen, syncLoading, syncPreview, syncOverwrite, prepareSync, confirmSync,
    f2mPageUrl, f2mCrawlLoading, crawlFilm2MediaDownloads,
    inputClass, textareaClass, afterSave,
  }
}

export type ContentEditor = ReturnType<typeof useContentEditor>