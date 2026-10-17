export type AppTheme = 'light' | 'dark'
export type ThemePreference = AppTheme | 'system'

// A new key on purpose: the old 'revayato-theme' was force-written to 'dark'
// for every visitor while the site was dark-only, so it says nothing about a
// real choice. The pre-paint script in nuxt.config.ts reads the same key.
const PREF_KEY = 'revayato-theme-pref'
const THEME_COLOR: Record<AppTheme, string> = { dark: '#1d1c21', light: '#f4f7f5' }

function systemTheme(): AppTheme {
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function readPref(): ThemePreference {
  try {
    const v = localStorage.getItem(PREF_KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  }
  catch {
    return 'system'
  }
}

function paint(theme: AppTheme) {
  const root = document.documentElement
  root.dataset.theme = theme
  root.style.colorScheme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme])
}

/**
 * Light / dark / follow-the-system. The pre-paint script already stamped the
 * right theme before first paint; this keeps it in sync afterwards.
 */
export function useTheme() {
  const preference = useState<ThemePreference>('app-theme-pref', () => 'system')
  const theme = useState<AppTheme>('app-theme', () => 'dark')
  const isDark = computed(() => theme.value === 'dark')

  function resolve() {
    theme.value = preference.value === 'system' ? systemTheme() : preference.value
    paint(theme.value)
  }

  function setPreference(next: ThemePreference) {
    preference.value = next
    try {
      if (next === 'system') localStorage.removeItem(PREF_KEY)
      else localStorage.setItem(PREF_KEY, next)
    }
    catch {
      // Without storage the choice lasts for this page view.
    }
    resolve()
  }

  /** Flip light ↔ dark with a quick circular reveal from the switch, when the browser can. */
  function toggleTheme(origin?: { x: number, y: number }) {
    const next: AppTheme = isDark.value ? 'light' : 'dark'
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const doc = document as Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } }
    if (!origin || reduce || !doc.startViewTransition) {
      setPreference(next)
      return
    }
    const r = Math.hypot(Math.max(origin.x, innerWidth - origin.x), Math.max(origin.y, innerHeight - origin.y))
    const vt = doc.startViewTransition(() => setPreference(next))
    vt.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${origin.x}px ${origin.y}px)`, `circle(${r}px at ${origin.x}px ${origin.y}px)`] },
        { duration: 380, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', pseudoElement: '::view-transition-new(root)' },
      )
    }).catch(() => {})
  }

  return { theme, isDark, preference, setPreference, toggleTheme, resolve }
}

/** Installed once from app.vue: reads the stored choice and follows OS changes. */
export function installTheme() {
  const { preference, resolve } = useTheme()
  onMounted(() => {
    preference.value = readPref()
    resolve()
    const mq = window.matchMedia?.('(prefers-color-scheme: light)')
    const onChange = () => {
      if (preference.value === 'system') resolve()
    }
    mq?.addEventListener?.('change', onChange)
    // Another tab changed the choice.
    const onStorage = (e: StorageEvent) => {
      if (e.key !== PREF_KEY) return
      preference.value = readPref()
      resolve()
    }
    window.addEventListener('storage', onStorage)
    onBeforeUnmount(() => {
      mq?.removeEventListener?.('change', onChange)
      window.removeEventListener('storage', onStorage)
    })
  })
}
