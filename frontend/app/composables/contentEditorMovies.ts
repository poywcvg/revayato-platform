import type { AdminEditorConfig, AdminItemApiLike } from '~/types/editorSchema'
import type { AdminMovie } from '~/types'

/**
 * Movie editor config — feeds the shared AdminContentEditor.
 * Sections mirror the legacy AdminMovieEditor (sticky sidebar + 6 sections).
 */
export function createMovieEditorConfig(): AdminEditorConfig {
  function api(): AdminItemApiLike {
    const movies = useAdminMovies()
    const provider = useProviderImport()
    return {
      ...movies,
      async crawlProviderDownloads(id, options) {
        const result = await provider.crawlMovieDownloads(id, options as { page_url?: string; replace?: boolean })
        return result as { imported_count: number; movie: AdminMovie; series?: never }
      },
    }
  }

  return {
    contentType: 'movie',
    api,
    listBackHref: '/admin/movies',
    newTitle: 'افزودن فیلم جدید',
    editTitle: 'ویرایش فیلم',
    contentNoun: 'فیلم',
    includes: {
      releaseYear: true,
      duration: true,
      releaseDate: true,
      spokenLanguages: true,
      trailer: true,
      videoUrl: true,
      downloadKey: true,
      tmdbSection: true,
      syncAvailable: true,
      seoSection: true,
      mediaStatus: true,
      isRecommended: true,
    },
    sections: [
      {
        id: 'basic',
        label: 'اطلاعات اصلی',
        fields: [
          { key: 'title', label: 'عنوان فارسی', type: 'text', required: true, placeholder: 'مثلاً جدایی نادر از سیمین' },
          { key: 'original_title', label: 'عنوان اصلی', type: 'text', dir: 'ltr', placeholder: 'Original title' },
          { key: 'slug', label: 'نامک (Slug)', type: 'text', dir: 'ltr', hint: 'اگر خالی بماند، سرور به‌صورت خودکار می‌سازد.', placeholder: 'movie-slug' },
          { key: 'catalog_type', label: 'نوع محتوا', type: 'select' },
          { key: 'short_description', label: 'خلاصه کوتاه', type: 'textarea', colSpan: 'sm:col-span-2', hint: 'برای کارت‌ها و نتایج جستجو؛ حداکثر ۵۰۰ نویسه.' },
          { key: 'description', label: 'معرفی کامل', type: 'textarea', colSpan: 'sm:col-span-2' },
        ],
      },
      {
        id: 'details',
        label: 'جزئیات انتشار',
        fields: [
          { key: 'release_date', label: 'تاریخ انتشار', type: 'date' },
          { key: 'release_year', label: 'سال انتشار', type: 'number', placeholder: '۱۳۸۰' },
          { key: 'duration_minutes', label: 'مدت (دقیقه)', type: 'number' },
          { key: 'age_rating', label: 'رده سنی', type: 'text', placeholder: 'مثلاً ۱۲+' },
          { key: 'language', label: 'زبان اصلی', type: 'text', placeholder: 'fa' },
          { key: 'content_format', label: 'فرمت', type: 'select' },
          { key: 'spoken_languages', label: 'زبان‌های گفتاری', type: 'text', colSpan: 'sm:col-span-2 lg:col-span-3', hint: 'با ویرگول جدا کنید.', placeholder: 'فارسی، انگلیسی' },
          { key: '__genres__', label: 'ژانرها', type: 'genres-picker' },
          { key: '__countries__', label: 'کشورها', type: 'countries-picker' },
          { key: '__availability__', type: 'availability-indicators' },
          { key: 'is_uncensored', label: 'نسخه بدون سانسور', type: 'checkbox' },
        ],
      },
      {
        id: 'media',
        label: 'رسانه',
        fields: [
          { key: '__poster__', label: 'پوستر عمودی', type: 'image-upload', kind: 'poster' },
          { key: '__backdrop__', label: 'تصویر پس‌زمینه', type: 'image-upload', kind: 'backdrop' },
          { key: 'trailer_external_url', label: 'آدرس تریلر خارجی', type: 'url', dir: 'ltr', placeholder: 'https://youtube.com/...' },
          { key: 'trailer_url', label: 'کلید داخلی تریلر', type: 'url', dir: 'ltr', placeholder: 'trailers/...' },
          { key: 'video_url', label: 'کلید یا آدرس HLS', type: 'url', dir: 'ltr', placeholder: 'movies/.../master.m3u8' },
          { key: 'download_key', label: 'کلید دانلود قدیمی (اختیاری)', type: 'text', dir: 'ltr', hint: 'فقط اگر هنوز از مسیر داخلی استفاده می‌کنید؛ برای لینک خارجی از جدول پایین استفاده کنید.', placeholder: 'اختیاری' },
          { key: 'quality', label: 'کیفیت پیش‌فرض', type: 'text', placeholder: '1080p' },
          { key: 'media_status', label: 'وضعیت رسانه', type: 'select' },
          { key: '__download_links__', label: 'لینک‌های دانلود', type: 'download-links' },
          { key: '__f2m__', type: 'f2m-crawl' },
        ],
      },
      {
        id: 'tmdb',
        label: 'TMDB و عوامل',
        fields: [
          { key: 'tmdb_id', label: 'TMDB ID', type: 'tmdb-id', dir: 'ltr' },
          { key: 'imdb_id', label: 'IMDb ID', type: 'imdb-id', dir: 'ltr', placeholder: 'tt1234567' },
          { key: 'imdb_rating', label: 'امتیاز IMDb', type: 'number', dir: 'ltr', placeholder: '۷.۸' },
          { key: '__sync__', type: 'sync-tmdb' },
          { key: '__crew__', type: 'crew-display' },
        ],
      },
      {
        id: 'seo',
        label: 'سئو',
        fields: [
          { key: 'meta_title', label: 'عنوان متا', type: 'text', hint: 'اگر خالی باشد، عنوان فیلم استفاده می‌شود.' },
          { key: 'meta_description', label: 'توضیح متا', type: 'textarea', hint: 'تا ۵۰۰ نویسه' },
          { key: 'seo_keywords', label: 'کلیدواژه‌ها', type: 'text', hint: 'با ویرگول جدا کنید.' },
        ],
      },
      {
        id: 'publishing',
        label: 'انتشار',
        fields: [
          { key: 'publication_status', label: 'وضعیت انتشار', type: 'radio-cards' },
          { key: 'is_featured', label: 'نمایش ویژه', type: 'checkbox' },
          { key: 'is_recommended', label: 'پیشنهاد تحریریه', type: 'checkbox' },
          { key: '__published_url__', type: 'published-url' },
        ],
      },
    ],
  }
}