import type { AdminEditorConfig } from '~/types/editorSchema'

/**
 * Series editor config — feeds the shared AdminContentEditor.
 * Uses the movie-style sticky sidebar layout, but keeps the series-specific
 * fields (status select, is_published checkbox, start/end year).
 */
export function createSeriesEditorConfig(): AdminEditorConfig {
  return {
    contentType: 'series',
    api: () => {
      const series = useAdminSeries()
      const provider = useProviderImport()
      return {
        ...series,
        discoverProvider: (id: number, options?: { force?: boolean }) => provider.discoverSeries(id, options),
      }
    },
    listBackHref: '/admin/series',
    newTitle: 'افزودن سریال جدید',
    editTitle: 'ویرایش سریال',
    contentNoun: 'سریال',
    includes: {
      releaseYear: false,
      duration: false,
      releaseDate: false,
      spokenLanguages: false,
      trailer: true,
      videoUrl: false,
      downloadKey: false,
      tmdbSection: true,
      syncAvailable: true,
      seoSection: false,
      mediaStatus: false,
      isRecommended: false,
    },
    sections: [
      {
        id: 'basic',
        label: 'اطلاعات اصلی',
        fields: [
          { key: 'title', label: 'عنوان فارسی', type: 'text', required: true, placeholder: 'مثلاً شهرزاد' },
          { key: 'original_title', label: 'عنوان اصلی', type: 'text', dir: 'ltr', placeholder: 'Original title' },
          { key: 'slug', label: 'نامک (Slug)', type: 'text', dir: 'ltr', hint: 'اگر خالی بماند، سرور به‌صورت خودکار می‌سازد.', placeholder: 'series-slug' },
          { key: 'status', label: 'وضعیت پخش', type: 'select' },
          { key: 'short_description', label: 'خلاصه کوتاه', type: 'textarea', colSpan: 'sm:col-span-2' },
          { key: 'description', label: 'معرفی کامل', type: 'textarea', colSpan: 'sm:col-span-2' },
        ],
      },
      {
        id: 'details',
        label: 'جزئیات',
        fields: [
          { key: 'start_year', label: 'سال شروع', type: 'number' },
          { key: 'end_year', label: 'سال پایان', type: 'number' },
          { key: 'age_rating', label: 'رده سنی', type: 'text' },
          { key: 'language', label: 'زبان', type: 'text' },
          { key: 'content_format', label: 'فرمت', type: 'select' },
          { key: 'tmdb_id', label: 'TMDB ID', type: 'tmdb-id', dir: 'ltr' },
          { key: 'imdb_id', label: 'IMDb ID', type: 'imdb-id', dir: 'ltr', placeholder: 'tt1234567' },
          { key: 'imdb_rating', label: 'امتیاز IMDb', type: 'number', dir: 'ltr', placeholder: '۷.۸' },
          { key: '__genres__', label: 'ژانرها', type: 'genres-picker' },
          { key: '__availability__', type: 'availability-indicators' },
          { key: 'is_uncensored', label: 'بدون سانسور', type: 'checkbox' },
        ],
      },
      {
        id: 'media',
        label: 'رسانه و دانلود',
        fields: [
          { key: '__poster__', label: 'آپلود پوستر', type: 'image-upload', kind: 'poster' },
          { key: '__backdrop__', label: 'آپلود پس‌زمینه', type: 'image-upload', kind: 'backdrop' },
          { key: 'poster_external_url', label: 'آدرس پوستر خارجی', type: 'url', dir: 'ltr' },
          { key: 'backdrop_external_url', label: 'آدرس پس‌زمینه خارجی', type: 'url', dir: 'ltr' },
          { key: 'trailer_external_url', label: 'آدرس تریلر خارجی', type: 'url', dir: 'ltr' },
          { key: 'trailer_url', label: 'کلید داخلی تریلر', type: 'url', dir: 'ltr' },
          { key: '__download_links__', label: 'لینک‌های دانلود', type: 'download-links' },
          { key: '__f2m__', type: 'f2m-crawl' },
        ],
      },
      {
        id: 'publishing',
        label: 'انتشار',
        fields: [
          { key: 'is_published', label: 'منتشر در سایت عمومی', type: 'checkbox' },
          { key: 'is_featured', label: 'ویژه / ترند', type: 'checkbox' },
          { key: '__published_url__', type: 'published-url' },
        ],
      },
    ],
  }
}