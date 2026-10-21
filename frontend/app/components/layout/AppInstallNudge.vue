<script setup lang="ts">
import Download from '~icons/lucide/download'
import Sparkles from '~icons/lucide/sparkles'
import X from '~icons/lucide/x'

const DISMISS_KEY = 'revayato:app-nudge-dismissed-until'
const VISITS_KEY = 'revayato:app-nudge-visits'
const visible = ref(false)
const { trackAppInstall } = useAnalyticsEvent()
const route = useRoute()

interface AppRelease {
  available?: boolean
  version_name?: string
  size_bytes?: number
}

// Mirrors the numbers surfaced on /app from the same `/api/app/version/`
// source (it only ever names an APK that is on disk); the constants are the
// floor before the call answers and if it never does.
const APP_VERSION_FALLBACK = '1.0.28'
const APP_SIZE_FALLBACK = '۳٫۴ مگابایت'
const { api } = useApi()
const release = ref<AppRelease | null>(null)
const APP_VERSION = computed(() => {
  const named = release.value?.available ? (release.value.version_name || '').trim() : ''
  return named || APP_VERSION_FALLBACK
})
const APP_SIZE = computed(() => {
  const bytes = release.value?.available ? Number(release.value.size_bytes || 0) : 0
  if (!bytes) return APP_SIZE_FALLBACK
  const mb = bytes / (1024 * 1024)
  const shown = mb < 10 ? Math.round(mb * 10) / 10 : Math.round(mb)
  return `${shown.toLocaleString('fa-IR')} مگابایت`
})

function dismissed() {
  try { return Number(localStorage.getItem(DISMISS_KEY) || 0) > Date.now() } catch { return false }
}

function dismiss() {
  visible.value = false
  try { localStorage.setItem(DISMISS_KEY, String(Date.now() + 21 * 24 * 60 * 60 * 1000)) } catch { /* optional */ }
  trackAppInstall('dismiss')
}

function openInstallPage() {
  trackAppInstall('click')
  visible.value = false
}

onMounted(() => {
  const agent = navigator.userAgent || ''
  // Android only: desktop/iOS users never get an irrelevant prompt. A short
  // delay and a three-page threshold keep the first visit uninterrupted.
  if (!/Android/i.test(agent) || /; wv\)/i.test(agent) || dismissed() || route.path.startsWith('/app')) return
  // Android gets the real version/size the moment the decision to show is
  // made; the 18s window below is ample for this one call.
  void api<AppRelease>('/app/version/').then((value) => { release.value = value }).catch(() => {})
  let visits = 0
  try {
    visits = Math.min(9, Number(sessionStorage.getItem(VISITS_KEY) || 0) + 1)
    sessionStorage.setItem(VISITS_KEY, String(visits))
  } catch { return }
  if (visits < 3) return
  window.setTimeout(() => {
    if (!document.hidden && !dismissed()) {
      visible.value = true
      trackAppInstall('prompt')
    }
  }, 18_000)
})

watch(() => route.path, (path) => {
  if (path.startsWith('/app')) visible.value = false
})
</script>

<template>
  <Transition name="app-nudge">
    <aside
      v-if="visible"
      class="app-nudge fixed inset-x-3 bottom-[calc(var(--mobile-bottom-nav-height)+env(safe-area-inset-bottom)+.75rem)] z-[70] mx-auto max-w-md overflow-hidden rounded-3xl p-[1px] lg:bottom-5"
      role="dialog"
      aria-label="دعوت به نصب اپلیکیشن اندروید روایتو"
    >
      <div class="relative rounded-[calc(1.5rem-1px)] bg-[color-mix(in_srgb,var(--theme-bg-elevated)_95%,transparent)] p-3.5">
        <button
          type="button"
          class="absolute end-2.5 top-2.5 grid size-8 place-items-center rounded-xl text-muted transition hover:bg-ink/8 hover:text-ink"
          aria-label="بستن دعوت نصب"
          @click="dismiss"
        >
          <X class="size-4" />
        </button>

        <div class="flex items-center gap-3 pe-8">
          <span class="app-nudge__icon relative grid size-14 shrink-0 place-items-center rounded-2xl bg-[#211b12] ring-1 ring-primary-300/25">
            <img src="/icon-192.png?v=2" alt="روایتو" width="56" height="56" class="size-14 rounded-2xl object-cover" >
            <span class="app-nudge__spark absolute -end-1 -top-1 grid size-5 place-items-center rounded-full bg-[var(--theme-accent-primary)] text-[var(--theme-on-accent)] ring-2 ring-[var(--theme-bg-elevated)]">
              <Sparkles class="size-3" />
            </span>
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-sm font-black text-ink">روایتو را همیشه همراهت داشته باش</p>
            <p class="mt-0.5 text-xs leading-5 text-muted">پخش سریع‌تر، دانلود آفلاین و ادامهٔ تماشا در اپ اندروید.</p>
          </div>
        </div>

        <div class="mt-2.5 flex flex-wrap items-center gap-1.5 ps-[68px]">
          <span class="inline-flex items-center gap-1 rounded-full bg-primary-400/12 px-2 py-0.5 text-[11px] font-black text-primary-200">رایگان</span>
          <span class="rounded-full bg-ink/6 px-2 py-0.5 text-[11px] font-bold text-muted">نسخه {{ APP_VERSION }}</span>
          <span class="rounded-full bg-ink/6 px-2 py-0.5 text-[11px] font-bold text-muted">{{ APP_SIZE }}</span>
          <span class="rounded-full bg-ink/6 px-2 py-0.5 text-[11px] font-bold text-muted">اندروید ۷+</span>
        </div>

        <div class="mt-3 flex items-center gap-2 ps-[68px]">
          <NuxtLink
            to="/app"
            class="app-nudge__cta inline-flex min-h-9 flex-1 items-center justify-center gap-1.5 rounded-xl bg-[var(--theme-accent-primary)] px-3 text-xs font-black text-[var(--theme-on-accent)] transition hover:brightness-105"
            @click="openInstallPage"
          >
            <Download class="size-3.5" />
            دریافت اپ اندروید
          </NuxtLink>
          <button type="button" class="min-h-9 shrink-0 px-2 text-xs font-bold text-muted transition hover:text-ink" @click="dismiss">فعلاً نه</button>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.app-nudge {
  background: linear-gradient(135deg, rgb(52 211 153 / 45%), color-mix(in srgb, var(--theme-text-primary) 6%, transparent) 55%, rgb(52 211 153 / 30%));
}
.app-nudge-enter-active,
.app-nudge-leave-active { transition: opacity .24s ease, transform .24s cubic-bezier(.22, 1, .36, 1); }
.app-nudge-enter-from,
.app-nudge-leave-to { opacity: 0; transform: translateY(14px) scale(.98); }
.app-nudge__spark { animation: nudge-spark 2.6s ease-in-out infinite; }
@keyframes nudge-spark {
  0%, 100% { transform: scale(1); opacity: .95; }
  50% { transform: scale(1.12); opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .app-nudge__spark { animation: none; }
  .app-nudge-enter-from,
  .app-nudge-leave-to { transform: none; }
}
</style>
