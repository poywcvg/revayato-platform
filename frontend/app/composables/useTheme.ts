export type AppTheme = 'dark'

const STORAGE_KEY = 'revayato-theme'
const FORCED_THEME: AppTheme = 'dark'

function applyDarkTheme() {
  if (!import.meta.client) return
  document.documentElement.dataset.theme = FORCED_THEME
  document.documentElement.style.colorScheme = FORCED_THEME
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', '#1d1c21')
  try {
    localStorage.setItem(STORAGE_KEY, FORCED_THEME)
  }
  catch {
    // Ignore storage failures (private mode, quota, etc.).
  }
}

/** Site theme is dark-only; light mode is disabled. */
export function useTheme() {
  const theme = useState<AppTheme>('app-theme', () => FORCED_THEME)

  const isDark = computed(() => true)

  function setTheme(_next?: AppTheme) {
    theme.value = FORCED_THEME
    applyDarkTheme()
  }

  function toggleTheme() {
    setTheme()
  }

  onMounted(() => {
    setTheme()
  })

  return { theme, isDark, setTheme, toggleTheme }
}
