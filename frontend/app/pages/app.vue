<script setup lang="ts">
import type { CinematicIconName } from '~/types'

// `/api/app/version/` is the same source of truth the installed app polls. The
// constants below are only the floor for the first paint and a failed request.
const APP_VERSION_FALLBACK = '1.0.28'
const APP_CODE_FALLBACK = 29
const APP_SIZE_FALLBACK = '۳٫۴ مگابایت'
const APK_URL_FALLBACK = '/downloads/revayato-1.0.28.apk'

interface AppRelease {
  available?: boolean
  version_name?: string
  version_code?: number
  download_url?: string
  size_bytes?: number
  sha256?: string
  released_at?: string
  notes?: string[]
  min_sdk?: number
}

const { api } = useApi()
const { data: release } = await useAsyncData<AppRelease | null>(
  'android-release',
  () => api<AppRelease>('/app/version/').catch(() => null),
  { default: () => null },
)

const faNum = (value: string | number) =>
  String(value).replace(/\d/g, digit => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)] ?? digit)

const APP_VERSION = computed(() => {
  const named = release.value?.available ? (release.value.version_name || '').trim() : ''
  return named || APP_VERSION_FALLBACK
})

const APP_CODE = computed(() => {
  const code = release.value?.available ? Number(release.value.version_code || 0) : 0
  return faNum(code || APP_CODE_FALLBACK)
})

const APK_URL = computed(() => {
  const url = release.value?.available ? (release.value.download_url || '').trim() : ''
  return url || APK_URL_FALLBACK
})

const APP_SIZE = computed(() => {
  const bytes = release.value?.available ? Number(release.value.size_bytes || 0) : 0
  if (!bytes) return APP_SIZE_FALLBACK
  const mb = bytes / (1024 * 1024)
  const shown = mb < 10 ? Math.round(mb * 10) / 10 : Math.round(mb)
  return `${faNum(shown.toLocaleString('fa-IR'))} مگابایت`
})

const MIN_ANDROID = computed(() => {
  const min = release.value?.available ? Number(release.value.min_sdk || 0) : 0
  if (!min || min <= 24) return 'اندروید ۷ و بالاتر'
  return `اندروید ${faNum(min)} و بالاتر`
})

const RELEASED_AT = computed(() => {
  const raw = release.value?.available ? release.value.released_at : ''
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw
  return new Intl.DateTimeFormat('fa-IR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(date)
})

const FILE_HASH = computed(() => {
  const hash = release.value?.available ? (release.value.sha256 || '').trim() : ''
  return hash || ''
})

const HASH_SHORT = computed(() => {
  if (!FILE_HASH.value) return 'در دسترس نیست'
  return `${FILE_HASH.value.slice(0, 16)}…`
})

const releaseNotes = computed(() =>
  (release.value?.notes || [])
    .filter(note => !/نصب دوباره|حذف نسخه|امضای امنیتی/.test(note))
    .slice(0, 5),
)

const features: { icon: CinematicIconName, title: string, text: string }[] = [
  {
    icon: 'play',
    title: 'پخش آنلاین روان',
    text: 'انتخاب کیفیت، منبع جایگزین خودکار و ادامهٔ تماشا از همان‌جایی که رها کردی.',
  },
  {
    icon: 'party',
    title: 'تماشای گروهی',
    text: 'یک اتاق بساز، لینک دعوت را بفرست و با دوستانت هم‌زمان و هماهنگ تماشا کن.',
  },
  {
    icon: 'subtitle',
    title: 'زیرنویس، مال خودت',
    text: 'فونت، اندازه، رنگ و جای زیرنویس را تغییر بده؛ تنظیمات برای دفعهٔ بعد می‌ماند.',
  },
  {
    icon: 'download',
    title: 'دانلود برای آفلاین',
    text: 'فیلم و قسمت‌ها را داخل اپ دانلود کن و بدون اینترنت ببین.',
  },
]

const steps = [
  {
    title: 'فایل را دانلود کن',
    text: 'دکمهٔ دانلود همین صفحه، آخرین نسخهٔ رسمی را مستقیم از سرور روایتو می‌گیرد.',
  },
  {
    title: 'اجازهٔ نصب بده',
    text: 'اگر اندروید خواست، برای مرورگر یا فایل‌منیجر «نصب برنامه‌های ناشناس» را فعال کن.',
  },
  {
    title: 'APK را باز کن',
    text: 'پنجرهٔ نصب را تأیید کن. اگر Play Protect هشدار داد، اجازهٔ بررسی و ادامه را بده.',
  },
  {
    title: 'وارد حساب شو',
    text: 'اپ را باز کن و با همان حساب روایتو وارد شو. تماشا و کالکشن‌هایت همراهت هستند.',
  },
]

const copied = ref<'link' | 'hash' | null>(null)
let copiedTimer: ReturnType<typeof setTimeout> | null = null

async function copyText(text: string, kind: 'link' | 'hash') {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = kind
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => (copied.value = null), 2200)
  } catch {
    copied.value = null
  }
}

function copyLink() {
  copyText(new URL(APK_URL.value, window.location.origin).toString(), 'link')
}

function copyHash() {
  if (FILE_HASH.value) copyText(FILE_HASH.value, 'hash')
}

useSeoMeta({
  title: 'اپلیکیشن اندروید روایتو',
  description:
    'نسخهٔ اندروید روایتو؛ پخش آنلاین، تماشای گروهی، زیرنویس قابل تنظیم و دانلود آفلاین. دانلود مستقیم APK و راهنمای نصب.',
  ogTitle: 'اپلیکیشن اندروید روایتو',
  ogDescription:
    'فیلم و سریال، همراه همیشگی تو. نسخهٔ اندروید روایتو را مستقیم دانلود کن.',
  ogType: 'website',
})
</script>

<template>
  <div class="app-download page-section pb-16" dir="rtl">
    <section class="app-hero render-later">
      <div class="app-hero__copy">
        <p class="app-eyebrow">
          <span class="app-eyebrow__dot" aria-hidden="true" />
          نسخهٔ اندروید · انتشار مستقیم
        </p>

        <h1 class="app-title">
          روایتو را
          <span>همراه داشته باش.</span>
        </h1>

        <p class="app-lead">
          فیلم و سریال، تماشای گروهی و زیرنویسی که خودت تنظیم می‌کنی؛ در یک اپ سبک
          که برای گوشی ساخته شده است. بدون فروشگاه، مستقیم از سرور روایتو.
        </p>

        <div class="app-actions">
          <a :href="APK_URL" download class="app-cta app-cta--ink">
            <CinematicIcon name="download" class="app-cta__icon" />
            <span class="app-cta__text">
              <strong>دانلود نسخه {{ APP_VERSION }}</strong>
              <small>{{ APP_SIZE }} · نصب مستقیم</small>
            </span>
          </a>
          <a href="#install" class="app-cta app-cta--quiet">راهنمای نصب</a>
        </div>

        <div class="app-trust">
          <span>
            <CinematicIcon name="smartphone" class="app-trust__icon" />
            {{ MIN_ANDROID }}
          </span>
          <span>
            <CinematicIcon name="shield-check" class="app-trust__icon" />
            امضای دیجیتال
          </span>
          <span>
            <CinematicIcon name="refresh" class="app-trust__icon" />
            به‌روزرسانی درون‌برنامه
          </span>
        </div>
      </div>

      <div class="app-visual">
        <div class="phone-frame" aria-hidden="true">
          <div class="phone-speaker" />
          <div class="phone-screen">
            <div class="phone-status">
              <span>۹:۴۱</span>
              <span class="phone-status__dots">•••</span>
            </div>
            <div class="phone-brand">
              <span class="phone-brand__mark">ر</span>
              روایتو
            </div>
            <div class="phone-hero">
              <span class="phone-hero__kicker">پیشنهاد امشب</span>
              <strong>یک شب،<br>یک فیلم.</strong>
              <span class="phone-hero__play">
                <CinematicIcon name="play" />
              </span>
            </div>
            <div class="phone-section-title">
              <span>تازه‌ها</span>
              <span>همه</span>
            </div>
            <div class="phone-rail">
              <span />
              <span />
              <span />
            </div>
            <div class="phone-nav">
              <span class="phone-nav__active" />
              <span />
              <span />
              <span />
              <span />
            </div>
          </div>
        </div>

        <div class="float-card float-card--party">
          <span class="float-card__icon">
            <CinematicIcon name="party" />
          </span>
          <span>
            <strong>تماشای گروهی</strong>
            <small>با دوستان، هم‌زمان</small>
          </span>
        </div>
        <div class="float-card float-card--sub">
          <span class="float-card__icon">
            <CinematicIcon name="subtitle" />
          </span>
          <span>
            <strong>زیرنویس دلخواه</strong>
            <small>فونت، رنگ و جای دلخواه</small>
          </span>
        </div>
      </div>
    </section>

    <section class="app-release render-later" aria-labelledby="release-title">
      <div class="app-section-head">
        <div>
          <p class="app-kicker">همین حالا</p>
          <h2 id="release-title">فایل واقعی، مشخصات واقعی</h2>
        </div>
        <a :href="APK_URL" download class="app-inline-link">
          دریافت APK
          <CinematicIcon name="arrow-up-right" class="app-inline-link__icon" />
        </a>
      </div>

      <div class="release-grid">
        <div class="release-card">
          <span>نسخه</span>
          <strong>{{ APP_VERSION }}</strong>
          <small>کد {{ APP_CODE }}</small>
        </div>
        <div class="release-card">
          <span>حجم فایل</span>
          <strong>{{ APP_SIZE }}</strong>
          <small>APK مستقیم</small>
        </div>
        <div class="release-card">
          <span>تاریخ انتشار</span>
          <strong>{{ RELEASED_AT || '—' }}</strong>
          <small>آخرین نسخهٔ پایدار</small>
        </div>
        <div class="release-card release-card--hash">
          <div class="release-card__hash-head">
            <span>SHA-256</span>
            <button
              type="button"
              class="release-copy"
              :disabled="!FILE_HASH"
              :aria-label="copied === 'hash' ? 'هش کپی شد' : 'کپی هش فایل'"
              @click="copyHash"
            >
              <CinematicIcon :name="copied === 'hash' ? 'check' : 'document'" class="release-copy__icon" />
              {{ copied === 'hash' ? 'کپی شد' : 'کپی هش' }}
            </button>
          </div>
          <code dir="ltr">{{ HASH_SHORT }}</code>
          <small>برای بررسی سلامت فایل پس از دانلود</small>
        </div>
      </div>

      <div v-if="releaseNotes.length" class="release-notes">
        <h3>در این نسخه</h3>
        <ul>
          <li v-for="note in releaseNotes" :key="note">
            <CinematicIcon name="check" class="release-notes__icon" />
            <span>{{ note }}</span>
          </li>
        </ul>
      </div>
    </section>

    <section class="app-features" aria-labelledby="features-title">
      <div class="app-section-head">
        <div>
          <p class="app-kicker">داخل اپ</p>
          <h2 id="features-title">برای تماشا، نه برای معطلی</h2>
        </div>
        <p class="app-section-head__note">
          هر چیزی که برای یک تماشای راحت لازم داری، در یک جا.
        </p>
      </div>

      <div class="feature-grid">
        <article v-for="(item, index) in features" :key="item.title" class="feature-card">
          <span class="feature-index">{{ faNum(String(index + 1).padStart(2, '0')) }}</span>
          <span class="feature-icon">
            <CinematicIcon :name="item.icon" />
          </span>
          <h3>{{ item.title }}</h3>
          <p>{{ item.text }}</p>
        </article>
      </div>
    </section>

    <section id="install" class="install-grid" aria-labelledby="install-title">
      <div class="install-panel">
        <div class="app-section-head app-section-head--compact">
          <div>
            <p class="app-kicker">در چند قدم</p>
            <h2 id="install-title">نصب روی اندروید</h2>
          </div>
          <span class="app-pill">حدود ۲ دقیقه</span>
        </div>

        <ol class="install-steps">
          <li v-for="(step, index) in steps" :key="step.title">
            <span class="install-step__number">{{ faNum(String(index + 1).padStart(2, '0')) }}</span>
            <div>
              <strong>{{ step.title }}</strong>
              <p>{{ step.text }}</p>
            </div>
          </li>
        </ol>

        <div class="install-note">
          <CinematicIcon name="info" class="install-note__icon" />
          <p>
            اندروید برای فایل‌های خارج از فروشگاه هشدار می‌دهد؛ این طبیعی است. فایل
            مستقیماً از سرور روایتو دانلود می‌شود و با امضای دیجیتال منتشر می‌شود.
          </p>
        </div>
      </div>

      <aside class="install-side">
        <div class="side-card">
          <p class="app-kicker">مشخصات فایل</p>
          <dl class="file-facts">
            <div>
              <dt>نام فایل</dt>
              <dd dir="ltr">revayato-{{ APP_VERSION }}.apk</dd>
            </div>
            <div>
              <dt>نسخه</dt>
              <dd>{{ APP_VERSION }} ({{ APP_CODE }})</dd>
            </div>
            <div>
              <dt>حداقل اندروید</dt>
              <dd>{{ MIN_ANDROID }}</dd>
            </div>
            <div>
              <dt>تاریخ انتشار</dt>
              <dd>{{ RELEASED_AT || '—' }}</dd>
            </div>
          </dl>
        </div>

        <div class="migration-card">
          <div class="migration-card__head">
            <span class="migration-card__icon">
              <CinematicIcon name="shield-alert" />
            </span>
            <strong>از نسخهٔ ۱٫۰٫۲۶ یا قدیمی‌تر می‌آیی؟</strong>
          </div>
          <p>
            به‌دلیل تغییر امضای امنیتی، این نسخه روی نسخه‌های خیلی قدیمی به‌صورت
            به‌روزرسانی معمولی نصب نمی‌شود. یک بار اپ قبلی را حذف کن و نسخهٔ جدید را
            نصب کن. حساب تو روی سرور باقی می‌ماند؛ فقط تنظیمات محلی دستگاه پاک می‌شود.
          </p>
        </div>

        <div class="side-card side-card--quiet">
          <p class="app-kicker">نسخه‌های بعدی</p>
          <p class="side-card__text">
            اپ از داخل خودش نسخهٔ جدید را پیدا می‌کند. کافی است یک بار نصبش کنی؛
            به‌روزرسانی‌های بعدی از همان‌جا می‌آیند.
          </p>
          <span class="side-card__meta">
            <CinematicIcon name="refresh" class="side-card__icon" />
            به‌روزرسانی خودکار
          </span>
        </div>
      </aside>
    </section>

    <section class="direct-card" aria-labelledby="direct-title">
      <div class="direct-card__copy">
        <p class="app-kicker">لینک مستقیم</p>
        <h2 id="direct-title">APK را جایی دیگر لازم داری؟</h2>
        <p>لینک فایل را کپی کن یا مستقیم از همین‌جا دانلود کن.</p>
      </div>
      <div class="direct-card__actions">
        <code dir="ltr" class="direct-card__url">{{ APK_URL }}</code>
        <div class="direct-card__buttons">
          <button type="button" class="app-button-quiet" @click="copyLink">
            <CinematicIcon :name="copied === 'link' ? 'check' : 'share'" class="app-button-quiet__icon" />
            {{ copied === 'link' ? 'لینک کپی شد' : 'کپی لینک' }}
          </button>
          <a :href="APK_URL" download class="app-cta app-cta--ink app-cta--small">
            <CinematicIcon name="download" class="app-cta__icon" />
            دانلود APK
          </a>
        </div>
      </div>
    </section>

    <p class="app-footnote">
      روایتو برای اندروید ۷ و بالاتر · {{ APP_SIZE }} · نسخهٔ {{ APP_VERSION }}
    </p>

    <p class="sr-only" aria-live="polite">
      {{ copied === 'link' ? 'لینک دانلود کپی شد' : copied === 'hash' ? 'هش فایل کپی شد' : '' }}
    </p>
  </div>
</template>

<style scoped>
.app-download {
  --app-line: var(--theme-border);
  --app-surface: var(--theme-bg-elevated);
  --app-surface-soft: var(--theme-bg-soft);
  --app-ink: var(--theme-text-primary);
  --app-secondary: var(--theme-text-secondary);
  --app-muted: var(--theme-text-muted);
  --app-accent: var(--theme-accent-primary);
  --app-on-accent: var(--theme-on-accent);
  color: var(--app-ink);
}

.app-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(17rem, 0.85fr);
  gap: clamp(1.5rem, 4vw, 3.5rem);
  align-items: center;
  overflow: hidden;
  padding: clamp(1.35rem, 4vw, 3.4rem);
  border: 1px solid var(--app-line);
  border-radius: 2rem;
  background:
    radial-gradient(circle at 82% 12%, color-mix(in srgb, var(--app-accent) 13%, transparent), transparent 34%),
    radial-gradient(circle at 10% 95%, color-mix(in srgb, var(--app-accent) 7%, transparent), transparent 38%),
    linear-gradient(135deg, var(--app-surface), var(--app-surface-soft));
}

.app-hero::after {
  content: '';
  position: absolute;
  inset: auto 12% 0 auto;
  width: 45%;
  height: 1px;
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--app-accent) 45%, transparent), transparent);
  opacity: 0.65;
  pointer-events: none;
}

.app-hero__copy {
  position: relative;
  z-index: 2;
  min-width: 0;
}

.app-eyebrow,
.app-kicker {
  margin: 0;
  color: var(--app-secondary);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.app-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.38rem 0.65rem;
  border: 1px solid color-mix(in srgb, var(--app-line) 80%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--app-surface) 55%, transparent);
}

.app-eyebrow__dot {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background: var(--app-accent);
}

.app-title {
  margin: 1rem 0 0;
  max-width: 13ch;
  color: var(--app-ink);
  font-size: clamp(2.15rem, 5vw, 4.2rem);
  font-weight: 900;
  line-height: 1.12;
  letter-spacing: -0.045em;
}

.app-title span {
  display: block;
  color: color-mix(in srgb, var(--app-ink) 62%, var(--app-accent));
}

.app-lead {
  max-width: 39rem;
  margin: 1.15rem 0 0;
  color: var(--app-secondary);
  font-size: clamp(0.92rem, 1.3vw, 1.02rem);
  line-height: 2;
}

.app-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  margin-top: 1.6rem;
}

.app-cta {
  display: inline-flex;
  min-height: 3.5rem;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 0.7rem 1.1rem;
  border: 1px solid transparent;
  border-radius: 1rem;
  font-weight: 800;
  line-height: 1.2;
  text-decoration: none;
  transition: transform 180ms ease, opacity 180ms ease, background-color 180ms ease;
}

.app-cta:hover {
  transform: translateY(-1px);
}

.app-cta:active {
  transform: translateY(0);
}

.app-cta:focus-visible,
.app-button-quiet:focus-visible,
.release-copy:focus-visible {
  outline: 2px solid var(--app-accent);
  outline-offset: 3px;
}

.app-cta--ink {
  background: var(--app-ink);
  color: var(--theme-bg-main);
  box-shadow: 0 18px 38px -28px rgb(0 0 0 / 55%);
}

.app-cta--quiet {
  border-color: var(--app-line);
  background: color-mix(in srgb, var(--app-surface) 55%, transparent);
  color: var(--app-ink);
}

.app-cta--quiet:hover {
  background: var(--app-surface);
}

.app-cta__icon {
  width: 1.2rem;
  height: 1.2rem;
  flex: 0 0 auto;
}

.app-cta__text {
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
  text-align: right;
}

.app-cta__text strong {
  font-size: 0.9rem;
}

.app-cta__text small {
  color: color-mix(in srgb, var(--theme-bg-main) 68%, transparent);
  font-size: 0.68rem;
  font-weight: 600;
}

.app-cta--small {
  min-height: 2.8rem;
  padding: 0.55rem 0.9rem;
  border-radius: 0.8rem;
  font-size: 0.82rem;
}

.app-trust {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 1rem;
  margin-top: 1.35rem;
  color: var(--app-secondary);
  font-size: 0.76rem;
  font-weight: 700;
}

.app-trust span {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.app-trust__icon {
  width: 1rem;
  height: 1rem;
  color: var(--app-accent);
}

.app-visual {
  position: relative;
  display: flex;
  min-height: 31rem;
  align-items: center;
  justify-content: center;
}

.phone-frame {
  position: relative;
  z-index: 1;
  width: min(17.2rem, 82%);
  aspect-ratio: 9 / 19;
  padding: 0.5rem;
  border: 1px solid rgb(255 255 255 / 13%);
  border-radius: 2.5rem;
  background: linear-gradient(150deg, #303634, #0b0e0d 55%, #1a211e);
  box-shadow:
    0 38px 80px -45px rgb(0 0 0 / 72%),
    inset 0 0 0 1px rgb(255 255 255 / 6%);
  transform: rotate(-3deg);
}

.phone-speaker {
  position: absolute;
  top: 0.78rem;
  left: 50%;
  z-index: 3;
  width: 4rem;
  height: 0.36rem;
  border-radius: 999px;
  background: #070908;
  transform: translateX(-50%);
}

.phone-screen {
  position: relative;
  display: flex;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
  padding: 1.35rem 0.82rem 0.9rem;
  border-radius: 2rem;
  background: #0c100e;
  color: #f3f7f4;
}

.phone-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.2rem;
  color: rgb(255 255 255 / 55%);
  font-size: 0.48rem;
  font-weight: 700;
}

.phone-status__dots {
  letter-spacing: 0.12em;
}

.phone-brand {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 1rem;
  font-size: 0.73rem;
  font-weight: 900;
}

.phone-brand__mark {
  display: grid;
  width: 1.15rem;
  height: 1.15rem;
  place-items: center;
  border-radius: 0.36rem;
  background: #d9a84e;
  color: #12100a;
  font-size: 0.6rem;
  font-weight: 900;
}

.phone-hero {
  position: relative;
  display: flex;
  min-height: 8.4rem;
  flex-direction: column;
  justify-content: flex-end;
  margin-top: 0.75rem;
  overflow: hidden;
  padding: 0.7rem;
  border-radius: 0.9rem;
  background:
    linear-gradient(180deg, transparent 12%, rgb(0 0 0 / 72%) 100%),
    radial-gradient(circle at 30% 20%, #5f7b6d, transparent 48%),
    linear-gradient(135deg, #2d4540, #101614);
}

.phone-hero__kicker {
  position: absolute;
  top: 0.6rem;
  right: 0.65rem;
  padding: 0.18rem 0.4rem;
  border: 1px solid rgb(255 255 255 / 18%);
  border-radius: 999px;
  background: rgb(0 0 0 / 28%);
  color: rgb(255 255 255 / 78%);
  font-size: 0.42rem;
  font-weight: 700;
}

.phone-hero strong {
  font-size: 1rem;
  font-weight: 900;
  line-height: 1.25;
}

.phone-hero__play {
  position: absolute;
  top: 50%;
  left: 50%;
  display: grid;
  width: 2rem;
  height: 2rem;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 30%);
  border-radius: 50%;
  background: rgb(255 255 255 / 14%);
  color: #fff;
  transform: translate(-50%, -50%);
}

.phone-hero__play :deep(svg) {
  width: 0.8rem;
  height: 0.8rem;
  margin-right: 0.1rem;
}

.phone-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.85rem;
  color: rgb(255 255 255 / 86%);
  font-size: 0.55rem;
  font-weight: 800;
}

.phone-section-title span:last-child {
  color: #8fd6b6;
  font-size: 0.45rem;
}

.phone-rail {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.4rem;
  margin-top: 0.45rem;
}

.phone-rail span {
  aspect-ratio: 0.72;
  border-radius: 0.5rem;
  background: linear-gradient(145deg, #40564d, #18221e);
}

.phone-rail span:nth-child(2) {
  background: linear-gradient(145deg, #5a4e3a, #221d16);
}

.phone-rail span:nth-child(3) {
  background: linear-gradient(145deg, #3d4c5c, #151b20);
}

.phone-nav {
  display: flex;
  align-items: center;
  justify-content: space-around;
  margin-top: auto;
  padding-top: 0.7rem;
  border-top: 1px solid rgb(255 255 255 / 8%);
}

.phone-nav span {
  width: 1rem;
  height: 0.3rem;
  border-radius: 999px;
  background: rgb(255 255 255 / 18%);
}

.phone-nav__active {
  width: 1.6rem !important;
  background: #8fd6b6 !important;
}

.float-card {
  position: absolute;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.6rem 0.72rem;
  border: 1px solid var(--app-line);
  border-radius: 0.9rem;
  background: color-mix(in srgb, var(--app-surface) 92%, transparent);
  box-shadow: 0 18px 36px -28px rgb(0 0 0 / 55%);
  backdrop-filter: blur(12px);
}

.float-card--party {
  top: 17%;
  right: -0.25rem;
}

.float-card--sub {
  bottom: 19%;
  left: -0.25rem;
}

.float-card__icon {
  display: grid;
  width: 1.75rem;
  height: 1.75rem;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 0.55rem;
  background: color-mix(in srgb, var(--app-accent) 12%, transparent);
  color: var(--app-accent);
}

.float-card__icon :deep(svg) {
  width: 0.9rem;
  height: 0.9rem;
}

.float-card strong,
.float-card small {
  display: block;
  white-space: nowrap;
}

.float-card strong {
  color: var(--app-ink);
  font-size: 0.65rem;
  font-weight: 800;
}

.float-card small {
  margin-top: 0.12rem;
  color: var(--app-secondary);
  font-size: 0.56rem;
  font-weight: 600;
}

.app-release {
  margin-top: 1rem;
  padding: clamp(1.15rem, 3vw, 1.75rem);
  border: 1px solid var(--app-line);
  border-radius: 1.6rem;
  background: var(--app-surface);
}

.app-section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.app-section-head--compact {
  margin-bottom: 0.4rem;
}

.app-section-head h2 {
  margin: 0.3rem 0 0;
  color: var(--app-ink);
  font-size: clamp(1.3rem, 2.4vw, 1.8rem);
  font-weight: 900;
  line-height: 1.25;
  letter-spacing: -0.03em;
}

.app-section-head__note {
  max-width: 22rem;
  margin: 0;
  color: var(--app-secondary);
  font-size: 0.8rem;
  line-height: 1.8;
  text-align: left;
}

.app-inline-link {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.3rem;
  color: var(--app-ink);
  font-size: 0.76rem;
  font-weight: 800;
  text-decoration: none;
}

.app-inline-link:hover {
  text-decoration: underline;
  text-underline-offset: 0.25rem;
}

.app-inline-link__icon {
  width: 0.9rem;
  height: 0.9rem;
}

.release-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
}

.release-card {
  min-width: 0;
  padding: 0.85rem 0.9rem;
  border: 1px solid var(--app-line);
  border-radius: 1rem;
  background: color-mix(in srgb, var(--app-surface-soft) 55%, transparent);
}

.release-card > span {
  display: block;
  color: var(--app-muted);
  font-size: 0.65rem;
  font-weight: 700;
}

.release-card > strong {
  display: block;
  overflow: hidden;
  margin-top: 0.25rem;
  color: var(--app-ink);
  font-size: 1rem;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.release-card > small {
  display: block;
  margin-top: 0.2rem;
  color: var(--app-secondary);
  font-size: 0.62rem;
  font-weight: 600;
}

.release-card--hash {
  grid-column: 1 / -1;
}

.release-card__hash-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.release-copy {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.45rem;
  border: 1px solid var(--app-line);
  border-radius: 0.45rem;
  background: transparent;
  color: var(--app-secondary);
  font: inherit;
  font-size: 0.62rem;
  font-weight: 700;
  cursor: pointer;
}

.release-copy:disabled {
  cursor: default;
  opacity: 0.5;
}

.release-copy__icon {
  width: 0.75rem;
  height: 0.75rem;
}

.release-card--hash code {
  display: block;
  overflow: hidden;
  margin-top: 0.5rem;
  color: var(--app-ink);
  font-size: 0.7rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.release-card--hash > small {
  margin-top: 0.3rem;
}

.release-notes {
  margin-top: 0.85rem;
  padding-top: 0.85rem;
  border-top: 1px solid var(--app-line);
}

.release-notes h3 {
  margin: 0 0 0.45rem;
  color: var(--app-ink);
  font-size: 0.78rem;
  font-weight: 900;
}

.release-notes ul {
  display: grid;
  gap: 0.35rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.release-notes li {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  color: var(--app-secondary);
  font-size: 0.73rem;
  line-height: 1.8;
}

.release-notes__icon {
  width: 0.78rem;
  height: 0.78rem;
  flex: 0 0 auto;
  margin-top: 0.38rem;
  color: var(--app-accent);
}

.app-features {
  margin-top: 2rem;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.7rem;
}

.feature-card {
  position: relative;
  min-width: 0;
  padding: 1.1rem;
  border: 1px solid var(--app-line);
  border-radius: 1.2rem;
  background: var(--app-surface);
}

.feature-index {
  position: absolute;
  top: 0.9rem;
  left: 1rem;
  color: color-mix(in srgb, var(--app-muted) 65%, transparent);
  font-size: 0.6rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.feature-icon {
  display: grid;
  width: 2.25rem;
  height: 2.25rem;
  place-items: center;
  border-radius: 0.7rem;
  background: color-mix(in srgb, var(--app-accent) 11%, transparent);
  color: var(--app-accent);
}

.feature-icon :deep(svg) {
  width: 1.05rem;
  height: 1.05rem;
}

.feature-card h3 {
  margin: 0.8rem 0 0;
  color: var(--app-ink);
  font-size: 0.9rem;
  font-weight: 900;
}

.feature-card p {
  margin: 0.4rem 0 0;
  color: var(--app-secondary);
  font-size: 0.76rem;
  line-height: 1.95;
}

.install-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(17rem, 0.85fr);
  gap: 0.8rem;
  margin-top: 2rem;
}

.install-panel,
.side-card,
.migration-card,
.direct-card {
  border: 1px solid var(--app-line);
  background: var(--app-surface);
}

.install-panel {
  padding: clamp(1.15rem, 3vw, 1.65rem);
  border-radius: 1.6rem;
}

.app-pill {
  flex: 0 0 auto;
  padding: 0.28rem 0.55rem;
  border: 1px solid color-mix(in srgb, var(--app-accent) 28%, var(--app-line));
  border-radius: 999px;
  background: color-mix(in srgb, var(--app-accent) 7%, transparent);
  color: var(--app-secondary);
  font-size: 0.65rem;
  font-weight: 700;
}

.install-steps {
  display: grid;
  gap: 0.15rem;
  margin: 1rem 0 0;
  padding: 0;
  list-style: none;
}

.install-steps li {
  display: grid;
  grid-template-columns: 1.8rem minmax(0, 1fr);
  gap: 0.65rem;
  align-items: start;
  padding: 0.65rem 0;
  border-bottom: 1px solid color-mix(in srgb, var(--app-line) 64%, transparent);
}

.install-steps li:last-child {
  border-bottom: 0;
}

.install-step__number {
  display: grid;
  width: 1.65rem;
  height: 1.65rem;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--app-accent) 10%, transparent);
  color: var(--app-secondary);
  font-size: 0.62rem;
  font-weight: 800;
}

.install-steps strong {
  display: block;
  color: var(--app-ink);
  font-size: 0.82rem;
  font-weight: 900;
}

.install-steps p {
  margin: 0.25rem 0 0;
  color: var(--app-secondary);
  font-size: 0.74rem;
  line-height: 1.9;
}

.install-note {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  margin-top: 0.9rem;
  padding: 0.7rem 0.8rem;
  border: 1px solid var(--app-line);
  border-radius: 0.85rem;
  background: var(--app-surface-soft);
}

.install-note__icon {
  width: 0.95rem;
  height: 0.95rem;
  flex: 0 0 auto;
  margin-top: 0.22rem;
  color: var(--app-accent);
}

.install-note p {
  margin: 0;
  color: var(--app-secondary);
  font-size: 0.7rem;
  line-height: 1.9;
}

.install-side {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.8rem;
}

.side-card,
.migration-card {
  padding: 1.05rem;
  border-radius: 1.3rem;
}

.file-facts {
  display: grid;
  gap: 0.55rem;
  margin: 0.7rem 0 0;
}

.file-facts div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid color-mix(in srgb, var(--app-line) 62%, transparent);
}

.file-facts div:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.file-facts dt {
  color: var(--app-muted);
  font-size: 0.68rem;
  font-weight: 700;
}

.file-facts dd {
  overflow: hidden;
  margin: 0;
  color: var(--app-ink);
  font-size: 0.7rem;
  font-weight: 800;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.migration-card {
  border-color: color-mix(in srgb, var(--app-accent) 30%, var(--app-line));
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--app-accent) 8%, transparent), transparent),
    var(--app-surface);
}

.migration-card__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.migration-card__icon {
  display: grid;
  width: 1.7rem;
  height: 1.7rem;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 0.5rem;
  background: color-mix(in srgb, var(--app-accent) 12%, transparent);
  color: var(--app-accent);
}

.migration-card__icon :deep(svg) {
  width: 0.9rem;
  height: 0.9rem;
}

.migration-card strong {
  color: var(--app-ink);
  font-size: 0.76rem;
  font-weight: 900;
  line-height: 1.6;
}

.migration-card p {
  margin: 0.55rem 0 0;
  color: var(--app-secondary);
  font-size: 0.7rem;
  line-height: 1.95;
}

.side-card--quiet {
  background: color-mix(in srgb, var(--app-surface-soft) 60%, var(--app-surface));
}

.side-card__text {
  margin: 0.45rem 0 0;
  color: var(--app-secondary);
  font-size: 0.72rem;
  line-height: 1.9;
}

.side-card__meta {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-top: 0.6rem;
  color: var(--app-muted);
  font-size: 0.65rem;
  font-weight: 700;
}

.side-card__icon {
  width: 0.8rem;
  height: 0.8rem;
  color: var(--app-accent);
}

.direct-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.25rem;
  margin-top: 0.8rem;
  padding: 1.15rem 1.25rem;
  border-radius: 1.4rem;
}

.direct-card__copy {
  min-width: 0;
}

.direct-card__copy h2 {
  margin: 0.28rem 0 0;
  color: var(--app-ink);
  font-size: 1.15rem;
  font-weight: 900;
}

.direct-card__copy p:last-child {
  margin: 0.3rem 0 0;
  color: var(--app-secondary);
  font-size: 0.73rem;
}

.direct-card__actions {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.5rem;
  align-items: flex-end;
}

.direct-card__url {
  display: block;
  overflow: hidden;
  max-width: 23rem;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--app-line);
  border-radius: 0.55rem;
  background: var(--app-surface-soft);
  color: var(--app-secondary);
  font-size: 0.65rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.direct-card__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  justify-content: flex-end;
}

.app-button-quiet {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 2.8rem;
  padding: 0.5rem 0.8rem;
  border: 1px solid var(--app-line);
  border-radius: 0.8rem;
  background: transparent;
  color: var(--app-ink);
  font: inherit;
  font-size: 0.75rem;
  font-weight: 800;
  cursor: pointer;
}

.app-button-quiet:hover {
  background: var(--app-surface-soft);
}

.app-button-quiet__icon {
  width: 0.9rem;
  height: 0.9rem;
}

.app-footnote {
  margin: 1.25rem 0 0;
  color: var(--app-muted);
  font-size: 0.68rem;
  text-align: center;
}

@media (max-width: 980px) {
  .app-hero {
    grid-template-columns: 1fr;
  }

  .app-title {
    max-width: 16ch;
  }

  .app-visual {
    min-height: 27rem;
    margin-top: 0.75rem;
  }

  .phone-frame {
    width: min(15.5rem, 74%);
  }

  .float-card--party {
    right: 2%;
  }

  .float-card--sub {
    left: 2%;
  }

  .install-grid {
    grid-template-columns: 1fr;
  }

  .direct-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .direct-card__actions {
    width: 100%;
    align-items: stretch;
  }

  .direct-card__url {
    max-width: 100%;
  }

  .direct-card__buttons {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .app-hero {
    border-radius: 1.5rem;
    padding: 1.15rem;
  }

  .app-title {
    font-size: 2.25rem;
  }

  .app-lead {
    line-height: 1.85;
  }

  .app-actions {
    flex-direction: column;
  }

  .app-cta {
    width: 100%;
  }

  .app-cta--quiet {
    min-height: 2.9rem;
  }

  .app-trust {
    gap: 0.45rem 0.8rem;
    font-size: 0.7rem;
  }

  .app-visual {
    min-height: 24rem;
  }

  .phone-frame {
    width: min(14.5rem, 78%);
  }

  .float-card {
    padding: 0.5rem 0.6rem;
  }

  .float-card--party {
    top: 13%;
    right: 0;
  }

  .float-card--sub {
    bottom: 12%;
    left: 0;
  }

  .float-card strong {
    font-size: 0.6rem;
  }

  .float-card small {
    font-size: 0.52rem;
  }

  .app-section-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.35rem;
  }

  .app-section-head__note {
    max-width: none;
  }

  .release-grid {
    grid-template-columns: 1fr;
  }

  .release-card--hash {
    grid-column: auto;
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }

  .install-panel,
  .side-card,
  .migration-card {
    border-radius: 1.1rem;
  }

  .direct-card {
    padding: 1rem;
  }

  .direct-card__buttons {
    flex-direction: column;
  }

  .app-button-quiet,
  .app-cta--small {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .app-cta,
  .app-button-quiet {
    transition-duration: 1ms;
  }

  .app-cta:hover,
  .app-cta:active {
    transform: none;
  }
}
</style>
