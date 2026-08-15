<script setup lang="ts">
import type { AppErrorDetails } from '~/types'

type AuthMode = 'login' | 'register'
type PasswordKey = 'login' | 'register' | 'confirm'

const props = withDefaults(defineProps<{
  initialMode?: AuthMode
}>(), {
  initialMode: 'login',
})

const authStore = useAuthStore()
const notifications = useNotifications()
const route = useRoute()

const mode = ref<AuthMode>(props.initialMode)
const loginIdentifier = ref('')
const loginPassword = ref('')
const rememberMe = ref(false)
const registerUsername = ref('')
const registerEmail = ref('')
const registerPassword = ref('')
const confirmPassword = ref('')
const acceptedTerms = ref(false)
const visiblePasswords = reactive<Record<PasswordKey, boolean>>({
  login: false,
  register: false,
  confirm: false,
})
const invalidFields = ref(new Set<string>())
const clientError = ref('')
const serverError = ref<AppErrorDetails | null>(null)
let focusTimer: number | undefined

const redirectPath = computed(() => {
  const value = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  return value.startsWith('/') && !value.startsWith('//') ? value : '/'
})

function isEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/u.test(value)
}

function isInvalid(field: string) {
  return invalidFields.value.has(field)
}

function clearField(field: string) {
  if (!invalidFields.value.has(field)) return
  const next = new Set(invalidFields.value)
  next.delete(field)
  invalidFields.value = next
  if (!next.size) clientError.value = ''
}

function showClientError(fields: string[], message: string) {
  invalidFields.value = new Set(fields)
  clientError.value = message
  serverError.value = null
  if (import.meta.client) {
    window.setTimeout(() => {
      document.querySelector<HTMLElement>(`[data-auth-field="${fields[0]}"]`)?.focus()
    }, 0)
  }
}

function clearErrors() {
  invalidFields.value = new Set()
  clientError.value = ''
  serverError.value = null
}

/**
 * The component remains mounted while this state changes. CSS performs the
 * 720ms panel slide and both form/text crossfades without route replacement.
 */
function switchMode(nextMode: AuthMode) {
  if (nextMode === mode.value) return

  mode.value = nextMode
  clearErrors()
  if (!import.meta.client) return

  window.clearTimeout(focusTimer)
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  focusTimer = window.setTimeout(() => {
    const target = nextMode === 'login' ? 'login-identifier' : 'register-username'
    document.getElementById(target)?.focus({ preventScroll: true })
  }, reduceMotion ? 0 : 740)
}

function togglePassword(key: PasswordKey) {
  visiblePasswords[key] = !visiblePasswords[key]
}

const USERNAME_PATTERN = /^[A-Za-z0-9_-]{3,150}$/

function validateUsernameClient(value: string) {
  const username = value.trim()
  if (!username) return 'نام کاربری را وارد کن.'
  if (username.length < 3) return 'نام کاربری باید حداقل ۳ کاراکتر باشد.'
  if (username.length > 150) return 'نام کاربری نباید بیشتر از ۱۵۰ کاراکتر باشد.'
  if (/\s/u.test(username)) return 'نام کاربری نباید فاصله داشته باشد.'
  if (!USERNAME_PATTERN.test(username)) {
    return 'نام کاربری فقط باید شامل حروف انگلیسی، عدد، "-" یا "_" باشد.'
  }
  return ''
}

async function submitLogin() {
  clearErrors()
  const identifier = loginIdentifier.value.trim()
  const fields: string[] = []

  if (identifier.length < 3) fields.push('loginIdentifier')
  if (loginPassword.value.length < 8) fields.push('loginPassword')
  if (fields.length) {
    showClientError(
      fields,
      fields[0] === 'loginIdentifier'
        ? 'ایمیل یا نام کاربری معتبر وارد کنید.'
        : 'رمز عبور باید حداقل ۸ کاراکتر داشته باشد.',
    )
    return
  }

  try {
    const user = await authStore.login(identifier, loginPassword.value)
    if (import.meta.client) {
      if (rememberMe.value) localStorage.setItem('revayato-login-identifier', identifier)
      else localStorage.removeItem('revayato-login-identifier')
    }
    notifications.success('خوش آمدی', `${user.username}، ورود با موفقیت انجام شد.`)
    await navigateTo(redirectPath.value)
  } catch (cause) {
    const details = getAppError(cause, 'ورود به حساب انجام نشد.')
    if (details.code === 'user_not_found') {
      if (isEmail(identifier)) registerEmail.value = identifier.toLowerCase()
      else registerUsername.value = identifier
      notifications.info('حساب پیدا نشد', 'می‌توانی همین حالا حساب تازه‌ای بسازی.')
      switchMode('register')
      return
    }
    serverError.value = details
    notifications.notifyFromDetails(details)
  }
}

async function submitRegister() {
  clearErrors()
  const username = registerUsername.value.trim()
  const email = registerEmail.value.trim().toLowerCase()
  const fields: string[] = []
  const usernameError = validateUsernameClient(registerUsername.value)

  if (usernameError) fields.push('registerUsername')
  if (!isEmail(email)) fields.push('registerEmail')
  if (registerPassword.value.length < 8) fields.push('registerPassword')
  if (!confirmPassword.value || confirmPassword.value !== registerPassword.value) fields.push('confirmPassword')
  if (!acceptedTerms.value) fields.push('terms')

  if (fields.length) {
    const messages: Record<string, string> = {
      registerUsername: usernameError || 'نام کاربری معتبر وارد کن.',
      registerEmail: 'یک ایمیل معتبر وارد کن.',
      registerPassword: 'رمز عبور باید حداقل ۸ کاراکتر داشته باشد.',
      confirmPassword: 'تکرار رمز عبور با رمز عبور یکسان نیست.',
      terms: 'برای ادامه، قوانین و حریم خصوصی را بپذیر.',
    }
    const firstField = fields[0]!
    showClientError(fields, messages[firstField] || 'اطلاعات فرم را بررسی کن.')
    return
  }

  try {
    const user = await authStore.register(email, username, registerPassword.value)
    notifications.success(
      'حساب ساخته شد',
      `${user.username}، حالا می‌توانی فهرست شخصی‌ات را بسازی.`,
      { inbox: true, href: '/profile' },
    )
    await navigateTo(redirectPath.value)
  } catch (cause) {
    const details = getAppError(cause, 'ساخت حساب انجام نشد.')
    serverError.value = details
    const usernameField = details.fields.find(item => item.field === 'username')
    if (usernameField) {
      invalidFields.value = new Set(['registerUsername'])
      clientError.value = usernameField.message
      if (import.meta.client) {
        window.setTimeout(() => {
          document.querySelector<HTMLElement>('[data-auth-field="registerUsername"]')?.focus()
        }, 0)
      }
    }
    notifications.notifyFromDetails(details)
  }
}

function notifyGoogle() {
  notifications.info('ورود با گوگل', 'این روش ورود به‌زودی فعال می‌شود.')
}

onMounted(() => {
  if (typeof route.query.mode === 'string' && ['login', 'register'].includes(route.query.mode)) {
    mode.value = route.query.mode as AuthMode
  }

  if (typeof route.query.email === 'string' && route.query.email.trim()) {
    registerEmail.value = route.query.email.trim().toLowerCase()
  }
  if (typeof route.query.username === 'string' && route.query.username.trim()) {
    registerUsername.value = route.query.username.trim()
  }

  try {
    const rememberedIdentifier = localStorage.getItem('revayato-login-identifier')
    if (rememberedIdentifier && !loginIdentifier.value) {
      loginIdentifier.value = rememberedIdentifier
      rememberMe.value = true
    }
  } catch {
    // Login remains fully usable when storage is blocked.
  }
})

onBeforeUnmount(() => window.clearTimeout(focusTimer))
</script>

<template>
  <section
    class="auth-portal"
    :class="{ 'is-register': mode === 'register' }"
    :aria-label="mode === 'login' ? 'ورود به حساب کاربری' : 'ساخت حساب کاربری'"
  >
    <div
      class="auth-form auth-form--login"
      :aria-hidden="mode !== 'login'"
      :inert="mode !== 'login' || undefined"
    >
      <div class="auth-form__inner">
        <header class="auth-heading">
          <span>خوش برگشتی</span>
          <h1>ورود به حساب</h1>
          <p>برای ادامه تماشای فیلم‌ها و سریال‌ها وارد شوید</p>
        </header>

        <form novalidate :aria-busy="authStore.pending" @submit.prevent="submitLogin">
          <div class="auth-fields">
            <div class="auth-field" :class="{ 'has-error': isInvalid('loginIdentifier') }">
              <label class="sr-only" for="login-identifier">ایمیل یا نام کاربری</label>
              <CinematicIcon name="user" class="auth-field__icon" aria-hidden="true" />
              <input
                id="login-identifier"
                v-model="loginIdentifier"
                data-auth-field="loginIdentifier"
                type="text"
                autocomplete="username"
                placeholder="ایمیل یا نام کاربری"
                :aria-invalid="isInvalid('loginIdentifier')"
                @input="clearField('loginIdentifier')"
              >
            </div>

            <div class="auth-field" :class="{ 'has-error': isInvalid('loginPassword') }">
              <label class="sr-only" for="login-password">رمز عبور</label>
              <CinematicIcon name="lock" class="auth-field__icon" aria-hidden="true" />
              <input
                id="login-password"
                v-model="loginPassword"
                data-auth-field="loginPassword"
                :type="visiblePasswords.login ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="رمز عبور"
                :aria-invalid="isInvalid('loginPassword')"
                @input="clearField('loginPassword')"
              >
              <button
                class="password-toggle"
                type="button"
                :aria-label="visiblePasswords.login ? 'پنهان کردن رمز عبور' : 'نمایش رمز عبور'"
                :aria-pressed="visiblePasswords.login"
                @click="togglePassword('login')"
              >
                <CinematicIcon :name="visiblePasswords.login ? 'eye-off' : 'eye'" />
              </button>
            </div>
          </div>

          <div class="auth-options">
            <label class="auth-check">
              <input v-model="rememberMe" type="checkbox">
              <span aria-hidden="true"><CinematicIcon name="check" /></span>
              ایمیل یا نام کاربری را به خاطر بسپار
            </label>
            <NuxtLink to="/auth/forgot-password">رمز عبور را فراموش کرده‌اید؟</NuxtLink>
          </div>

          <p v-if="clientError" class="auth-alert" role="alert">{{ clientError }}</p>
          <p v-else-if="serverError" class="auth-alert" role="alert">
            {{ serverError.reason || serverError.message }}
          </p>

          <button class="auth-primary" type="submit" :disabled="authStore.pending">
            <span v-if="authStore.pending" class="auth-spinner" aria-hidden="true" />
            <template v-else>
              <span>ورود به روایتو</span>
              <CinematicIcon name="arrow-left" />
            </template>
          </button>

          <div class="auth-divider" role="separator"><span>یا</span></div>

          <button class="auth-google" type="button" @click="notifyGoogle">
            <span class="google-mark" aria-hidden="true"><i /><i /><i /><i /></span>
            ادامه با گوگل
          </button>

          <p class="auth-mobile-switch">
            حساب کاربری ندارید؟
            <button type="button" @click="switchMode('register')">ثبت‌نام کنید</button>
          </p>
        </form>
      </div>
    </div>

    <div
      class="auth-form auth-form--register"
      :aria-hidden="mode !== 'register'"
      :inert="mode !== 'register' || undefined"
    >
      <div class="auth-form__inner auth-form__inner--register">
        <header class="auth-heading auth-heading--compact">
          <span>شروع یک ماجرا</span>
          <h2>ساخت حساب کاربری</h2>
          <p>به دنیای فیلم و سریال بپیوندید</p>
        </header>

        <form novalidate :aria-busy="authStore.pending" @submit.prevent="submitRegister">
          <div class="auth-fields auth-fields--compact">
            <div class="auth-field" :class="{ 'has-error': isInvalid('registerUsername') }">
              <label class="sr-only" for="register-username">نام کاربری</label>
              <CinematicIcon name="user" class="auth-field__icon" aria-hidden="true" />
              <input
                id="register-username"
                v-model="registerUsername"
                data-auth-field="registerUsername"
                type="text"
                dir="ltr"
                autocomplete="username"
                spellcheck="false"
                placeholder="نام کاربری (همان‌طور که می‌نویسی ثبت می‌شود)"
                :aria-invalid="isInvalid('registerUsername')"
                @input="clearField('registerUsername')"
              >
            </div>

            <div class="auth-field" :class="{ 'has-error': isInvalid('registerEmail') }">
              <label class="sr-only" for="register-email">ایمیل</label>
              <CinematicIcon name="login" class="auth-field__icon" aria-hidden="true" />
              <input
                id="register-email"
                v-model="registerEmail"
                data-auth-field="registerEmail"
                type="email"
                inputmode="email"
                autocomplete="email"
                placeholder="ایمیل"
                :aria-invalid="isInvalid('registerEmail')"
                @input="clearField('registerEmail')"
              >
            </div>

            <div class="auth-field" :class="{ 'has-error': isInvalid('registerPassword') }">
              <label class="sr-only" for="register-password">رمز عبور</label>
              <CinematicIcon name="lock" class="auth-field__icon" aria-hidden="true" />
              <input
                id="register-password"
                v-model="registerPassword"
                data-auth-field="registerPassword"
                :type="visiblePasswords.register ? 'text' : 'password'"
                autocomplete="new-password"
                placeholder="رمز عبور؛ حداقل ۸ کاراکتر"
                :aria-invalid="isInvalid('registerPassword')"
                @input="clearField('registerPassword')"
              >
              <button
                class="password-toggle"
                type="button"
                :aria-label="visiblePasswords.register ? 'پنهان کردن رمز عبور' : 'نمایش رمز عبور'"
                :aria-pressed="visiblePasswords.register"
                @click="togglePassword('register')"
              >
                <CinematicIcon :name="visiblePasswords.register ? 'eye-off' : 'eye'" />
              </button>
            </div>

            <div class="auth-field" :class="{ 'has-error': isInvalid('confirmPassword') }">
              <label class="sr-only" for="confirm-password">تکرار رمز عبور</label>
              <CinematicIcon name="lock" class="auth-field__icon" aria-hidden="true" />
              <input
                id="confirm-password"
                v-model="confirmPassword"
                data-auth-field="confirmPassword"
                :type="visiblePasswords.confirm ? 'text' : 'password'"
                autocomplete="new-password"
                placeholder="تکرار رمز عبور"
                :aria-invalid="isInvalid('confirmPassword')"
                @input="clearField('confirmPassword')"
              >
              <button
                class="password-toggle"
                type="button"
                :aria-label="visiblePasswords.confirm ? 'پنهان کردن رمز عبور' : 'نمایش رمز عبور'"
                :aria-pressed="visiblePasswords.confirm"
                @click="togglePassword('confirm')"
              >
                <CinematicIcon :name="visiblePasswords.confirm ? 'eye-off' : 'eye'" />
              </button>
            </div>
          </div>

          <label class="auth-check auth-terms" :class="{ 'has-error': isInvalid('terms') }">
            <input
              v-model="acceptedTerms"
              data-auth-field="terms"
              type="checkbox"
              @change="clearField('terms')"
            >
            <span aria-hidden="true"><CinematicIcon name="check" /></span>
            <span>
              <NuxtLink to="/terms">قوانین استفاده</NuxtLink>
              و
              <NuxtLink to="/privacy">حریم خصوصی</NuxtLink>
              را می‌پذیرم
            </span>
          </label>

          <p v-if="clientError" class="auth-alert" role="alert">{{ clientError }}</p>
          <p v-else-if="serverError" class="auth-alert" role="alert">
            {{ serverError.reason || serverError.message }}
          </p>

          <button class="auth-primary" type="submit" :disabled="authStore.pending">
            <span v-if="authStore.pending" class="auth-spinner" aria-hidden="true" />
            <template v-else>
              <span>ساخت حساب کاربری</span>
              <CinematicIcon name="arrow-left" />
            </template>
          </button>

          <div class="auth-divider" role="separator"><span>یا</span></div>

          <button class="auth-google" type="button" @click="notifyGoogle">
            <span class="google-mark" aria-hidden="true"><i /><i /><i /><i /></span>
            ثبت‌نام با گوگل
          </button>

          <p class="auth-mobile-switch">
            قبلاً حساب ساخته‌اید؟
            <button type="button" @click="switchMode('login')">وارد شوید</button>
          </p>
        </form>
      </div>
    </div>

    <!-- Sliding cinematic panel: transform handles the full half-card movement. -->
    <aside class="auth-cinema-panel" aria-label="تغییر حالت ورود و ثبت‌نام">
      <div class="auth-cinema-panel__grain" aria-hidden="true" />
      <div class="auth-cinema-panel__light" aria-hidden="true" />
      <div class="auth-film-strip" aria-hidden="true">
        <i v-for="index in 6" :key="index" />
      </div>

      <div class="auth-play" aria-hidden="true">
        <span>
          <svg viewBox="0 0 42 42">
            <path d="m16 12 15 9-15 9V12Z" fill="currentColor" />
          </svg>
        </span>
        <i />
        <i />
      </div>

      <div class="auth-panel-copy auth-panel-copy--register" :aria-hidden="mode !== 'login'">
        <small>عضویت در روایتو</small>
        <h2>اولین باره اینجایی؟</h2>
        <p>همین حالا حساب بساز و لیست تماشای شخصی خودت را ایجاد کن</p>
        <button type="button" @click="switchMode('register')">
          ثبت نام
          <CinematicIcon name="arrow-left" />
        </button>
      </div>

      <div class="auth-panel-copy auth-panel-copy--login" :aria-hidden="mode !== 'register'">
        <small>ادامهٔ تماشا</small>
        <h2>دوباره خوش اومدی</h2>
        <p>وارد حسابت شو و تماشای فیلم‌ها و سریال‌های مورد علاقه‌ات را ادامه بده</p>
        <button type="button" @click="switchMode('login')">
          ورود
          <CinematicIcon name="arrow-left" />
        </button>
      </div>
    </aside>
  </section>
</template>

<style scoped>
.auth-portal {
  --auth-accent: var(--palette-sand);
  --auth-accent-bright: var(--theme-accent-primary-hover);
  --auth-accent-mid: var(--palette-mid);
  --auth-accent-deep: var(--palette-deep);
  --auth-time: 720ms;
  --auth-ease: cubic-bezier(.76, 0, .24, 1);
  position: relative;
  width: min(920px, 100%);
  height: 540px;
  overflow: hidden;
  border: 1px solid var(--theme-border);
  border-radius: 28px;
  background: linear-gradient(145deg, color-mix(in srgb, var(--theme-bg-elevated) 96%, transparent), color-mix(in srgb, var(--theme-bg-main) 98%, transparent));
  box-shadow: 0 34px 90px rgb(0 0 0 / 58%), 0 10px 30px rgb(0 0 0 / 36%);
  color: var(--theme-text-primary);
  isolation: isolate;
}

.auth-portal::before {
  position: absolute;
  z-index: 2;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(120deg, rgb(255 255 255 / 7%), transparent 18% 82%, rgb(255 255 255 / 2%));
  content: "";
  pointer-events: none;
}

.auth-form {
  position: absolute;
  z-index: 5;
  top: 0;
  width: 50%;
  height: 100%;
  transition:
    opacity calc(var(--auth-time) * .62) ease,
    transform var(--auth-time) var(--auth-ease),
    filter calc(var(--auth-time) * .62) ease;
  will-change: opacity, transform;
}

.auth-form--login {
  right: 0;
  opacity: 1;
}

.auth-form--register {
  left: 0;
  opacity: 0;
  pointer-events: none;
  filter: blur(3px);
  transform: translateX(54px);
}

.is-register .auth-form--login {
  opacity: 0;
  pointer-events: none;
  filter: blur(3px);
  transform: translateX(-54px);
}

.is-register .auth-form--register {
  opacity: 1;
  pointer-events: auto;
  filter: none;
  transform: translateX(0);
}

.auth-form__inner {
  display: flex;
  height: 100%;
  padding: 36px 52px 27px;
  flex-direction: column;
  justify-content: center;
}

.auth-form__inner--register {
  padding-block: 21px 17px;
}

.auth-heading {
  margin-bottom: 23px;
  text-align: right;
}

.auth-heading--compact {
  margin-bottom: 13px;
}

.auth-heading > span {
  display: block;
  margin-bottom: 4px;
  color: var(--auth-accent);
  font-size: .69rem;
  font-weight: 800;
}

.auth-heading h1,
.auth-heading h2 {
  margin: 0 0 6px;
  color: var(--theme-text-primary);
  font-size: clamp(1.65rem, 3vw, 2rem);
  font-weight: 900;
  letter-spacing: -.045em;
}

.auth-heading p {
  margin: 0;
  color: var(--theme-text-secondary);
  font-size: .79rem;
  line-height: 1.8;
}

.auth-fields {
  display: grid;
  gap: 11px;
}

.auth-fields--compact {
  gap: 7px;
}

.auth-field {
  position: relative;
}

.auth-field input {
  width: 100%;
  height: 48px;
  padding: 0 43px 0 47px;
  outline: 0;
  border: 1px solid var(--theme-border);
  border-radius: 13px;
  background: rgb(255 255 255 / 4%);
  color: var(--theme-text-primary);
  caret-color: var(--auth-accent);
  font-size: .78rem;
  font-weight: 500;
  text-align: right;
  transition: border-color 220ms ease, background 220ms ease, box-shadow 220ms ease, transform 220ms ease;
}

.auth-fields--compact .auth-field input {
  height: 43px;
}

.auth-field input::placeholder {
  color: var(--theme-text-disabled);
}

.auth-field input:hover {
  border-color: rgb(var(--palette-sand-rgb) / 22%);
  background: rgb(255 255 255 / 6%);
}

.auth-field input:focus {
  border-color: rgb(var(--palette-sand-rgb) / 55%);
  background: var(--theme-accent-primary-soft);
  box-shadow: 0 0 0 4px rgb(var(--palette-sand-rgb) / 12%);
  transform: translateY(-1px);
}

.auth-field__icon {
  position: absolute;
  z-index: 2;
  top: 50%;
  right: 15px;
  width: 17px;
  height: 17px;
  color: var(--theme-text-muted);
  pointer-events: none;
  transform: translateY(-50%);
  transition: color 220ms ease;
}

.auth-field:focus-within .auth-field__icon {
  color: var(--auth-accent);
}

.auth-field.has-error input {
  border-color: color-mix(in srgb, var(--theme-error) 72%, transparent);
  background: color-mix(in srgb, var(--theme-error) 8%, transparent);
}

.password-toggle {
  position: absolute;
  z-index: 3;
  top: 50%;
  left: 8px;
  display: grid;
  width: 34px;
  height: 34px;
  padding: 0;
  place-items: center;
  border-radius: 9px;
  background: transparent;
  color: var(--theme-text-muted);
  transform: translateY(-50%);
}

.password-toggle:hover,
.password-toggle:focus-visible {
  background: rgb(255 255 255 / 7%);
  color: var(--theme-text-primary);
}

.password-toggle :deep(svg) {
  width: 18px;
  height: 18px;
}

.auth-options {
  display: flex;
  margin: 14px 0;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--theme-text-secondary);
  font-size: .69rem;
}

.auth-options a {
  color: var(--theme-text-secondary);
}

.auth-options a:hover {
  color: var(--auth-accent);
}

.auth-check {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--theme-text-secondary);
  cursor: pointer;
  font-size: .69rem;
  line-height: 1.6;
  user-select: none;
}

.auth-check input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.auth-check > span:first-of-type {
  display: grid;
  width: 17px;
  height: 17px;
  flex: 0 0 17px;
  place-items: center;
  border: 1px solid rgb(var(--palette-sand-rgb) / 22%);
  border-radius: 5px;
  background: rgb(255 255 255 / 4%);
  transition: border-color 180ms ease, background 180ms ease, box-shadow 180ms ease;
}

.auth-check > span:first-of-type :deep(svg) {
  width: 11px;
  height: 11px;
  color: var(--theme-bg-main);
  opacity: 0;
  transform: scale(.45);
  transition: opacity 180ms ease, transform 180ms ease;
}

.auth-check input:checked + span {
  border-color: var(--auth-accent-mid);
  background: var(--auth-accent);
  box-shadow: 0 4px 14px rgb(var(--palette-sand-rgb) / 22%);
}

.auth-check input:checked + span :deep(svg) {
  opacity: 1;
  transform: scale(1);
}

.auth-check input:focus-visible + span {
  box-shadow: 0 0 0 4px rgb(var(--palette-sand-rgb) / 14%);
}

.auth-check.has-error > span:first-of-type {
  border-color: var(--theme-error);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--theme-error) 12%, transparent);
}

.auth-terms {
  margin: 9px 0;
  align-items: flex-start;
}

.auth-terms a {
  color: var(--theme-text-primary);
  text-decoration: underline;
  text-decoration-color: rgb(var(--palette-sand-rgb) / 30%);
  text-underline-offset: 3px;
}

.auth-alert {
  min-height: 19px;
  margin: -3px 0 7px;
  color: var(--theme-error);
  font-size: .65rem;
  font-weight: 600;
  line-height: 1.65;
  text-align: center;
}

.auth-primary,
.auth-google {
  position: relative;
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.auth-primary {
  height: 47px;
  padding: 0 19px;
  gap: 9px;
  overflow: hidden;
  border: 1px solid rgb(var(--palette-sand-rgb) / 18%);
  border-radius: 13px;
  background: linear-gradient(135deg, var(--auth-accent-bright), var(--auth-accent) 48%, var(--auth-accent-mid));
  box-shadow: 0 12px 28px rgb(var(--palette-mid-rgb) / 28%), inset 0 1px rgb(255 255 255 / 17%);
  color: var(--theme-bg-main);
  font-size: .8rem;
  font-weight: 800;
  transition: transform 210ms ease, filter 210ms ease, box-shadow 210ms ease;
}

.auth-primary::before {
  position: absolute;
  top: -80%;
  left: -50%;
  width: 34%;
  height: 260%;
  background: rgb(255 255 255 / 18%);
  content: "";
  filter: blur(5px);
  transform: rotate(23deg);
  transition: left 520ms ease;
}

.auth-primary:hover:not(:disabled) {
  box-shadow: 0 16px 34px rgb(var(--palette-mid-rgb) / 36%), inset 0 1px rgb(255 255 255 / 18%);
  filter: brightness(1.05);
  transform: translateY(-2px);
}

.auth-primary:hover::before {
  left: 115%;
}

.auth-primary :deep(svg) {
  width: 18px;
  height: 18px;
  transition: transform 200ms ease;
}

.auth-primary:hover :deep(svg) {
  transform: translateX(-3px);
}

.auth-spinner {
  width: 19px;
  height: 19px;
  border: 2px solid rgb(var(--palette-void-rgb) / 28%);
  border-top-color: var(--theme-bg-main);
  border-radius: 50%;
  animation: auth-spin 650ms linear infinite;
}

@keyframes auth-spin {
  to { transform: rotate(360deg); }
}

.auth-divider {
  display: flex;
  margin: 9px 0;
  align-items: center;
  gap: 10px;
  color: var(--theme-text-disabled);
  font-size: .65rem;
}

.auth-divider::before,
.auth-divider::after {
  height: 1px;
  background: linear-gradient(90deg, transparent, rgb(255 255 255 / 12%));
  content: "";
  flex: 1;
}

.auth-divider::after {
  background: linear-gradient(90deg, rgb(255 255 255 / 12%), transparent);
}

.auth-google {
  height: 43px;
  gap: 10px;
  border: 1px solid var(--theme-border);
  border-radius: 13px;
  background: rgb(255 255 255 / 4%);
  color: var(--theme-text-primary);
  font-size: .75rem;
  font-weight: 600;
  transition: border-color 200ms ease, background 200ms ease, transform 200ms ease;
}

.auth-google:hover {
  border-color: rgb(var(--palette-sand-rgb) / 28%);
  background: var(--theme-accent-primary-soft);
  transform: translateY(-2px);
}

.google-mark {
  position: relative;
  display: block;
  width: 17px;
  height: 17px;
  transform: rotate(45deg);
}

.google-mark i {
  position: absolute;
  width: 7px;
  height: 7px;
  border-radius: 2px;
}

.google-mark i:nth-child(1) { top: 0; right: 0; background: #4285f4; }
.google-mark i:nth-child(2) { top: 0; left: 0; background: #ea4335; }
.google-mark i:nth-child(3) { right: 0; bottom: 0; background: #34a853; }
.google-mark i:nth-child(4) { bottom: 0; left: 0; background: #fbbc05; }

.auth-mobile-switch {
  display: none;
  margin: 13px 0 0;
  color: var(--theme-text-muted);
  font-size: .7rem;
  text-align: center;
}

.auth-mobile-switch button {
  padding: 0 3px;
  background: transparent;
  color: var(--auth-accent);
  font-weight: 800;
}

/* Sliding panel and its copy use only transforms/opacity, never abrupt display changes. */
.auth-cinema-panel {
  position: absolute;
  z-index: 15;
  top: 0;
  left: 0;
  width: 50%;
  height: 100%;
  overflow: hidden;
  border-radius: 28px 0 0 28px;
  background:
    radial-gradient(circle at 78% 19%, rgb(var(--palette-sand-rgb) / 28%), transparent 26%),
    radial-gradient(circle at 18% 88%, rgb(var(--palette-void-rgb) / 62%), transparent 36%),
    linear-gradient(145deg, var(--palette-mid) 0%, var(--palette-deep) 47%, #06241c 100%);
  box-shadow: 18px 0 45px rgb(0 0 0 / 28%);
  transition:
    transform var(--auth-time) var(--auth-ease),
    border-radius var(--auth-time) var(--auth-ease),
    box-shadow var(--auth-time) var(--auth-ease);
  will-change: transform;
}

.is-register .auth-cinema-panel {
  border-radius: 0 28px 28px 0;
  box-shadow: -18px 0 45px rgb(0 0 0 / 28%);
  transform: translateX(100%);
}

.auth-cinema-panel::before {
  position: absolute;
  top: -235px;
  left: -75px;
  width: 380px;
  height: 380px;
  border: 1px solid rgb(255 255 255 / 12%);
  border-radius: 50%;
  box-shadow: 0 0 0 35px rgb(255 255 255 / 2%), 0 0 0 74px rgb(255 255 255 / 1.5%);
  content: "";
}

.auth-cinema-panel::after {
  position: absolute;
  right: -38px;
  bottom: -62px;
  width: 230px;
  height: 230px;
  border-radius: 50%;
  background: var(--theme-bg-main);
  box-shadow: inset 0 0 45px rgb(255 255 255 / 4%), 0 0 80px rgb(var(--palette-void-rgb) / 45%);
  content: "";
  opacity: .42;
}

.auth-cinema-panel__grain {
  position: absolute;
  z-index: 2;
  inset: 0;
  opacity: .14;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 120 120' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='1.1' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.45'/%3E%3C/svg%3E");
  mix-blend-mode: overlay;
  pointer-events: none;
}

.auth-cinema-panel__light {
  position: absolute;
  z-index: 1;
  top: -80px;
  right: 80px;
  width: 180px;
  height: 460px;
  background: linear-gradient(180deg, rgb(255 255 255 / 20%), transparent 84%);
  clip-path: polygon(45% 0, 55% 0, 100% 100%, 0 100%);
  filter: blur(14px);
  opacity: .34;
  transform: rotate(-18deg);
}

.auth-film-strip {
  position: absolute;
  z-index: 3;
  top: 22px;
  left: -12px;
  display: flex;
  width: 210px;
  height: 34px;
  padding: 6px 9px;
  align-items: center;
  gap: 8px;
  border-block: 1px solid rgb(255 255 255 / 12%);
  opacity: .35;
  transform: rotate(-16deg);
}

.auth-film-strip i {
  width: 21px;
  height: 17px;
  flex: 0 0 21px;
  border: 1px solid rgb(255 255 255 / 25%);
  border-radius: 2px;
  background: rgb(var(--palette-void-rgb) / 22%);
}

.auth-play {
  position: absolute;
  z-index: 4;
  top: 78px;
  left: 50%;
  width: 98px;
  height: 98px;
  transform: translateX(-50%);
}

.auth-play > span {
  position: absolute;
  z-index: 2;
  inset: 14px;
  display: grid;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 27%);
  border-radius: 50%;
  background: rgb(var(--palette-void-rgb) / 28%);
  box-shadow: inset 0 0 20px rgb(255 255 255 / 8%), 0 12px 35px rgb(var(--palette-void-rgb) / 30%);
  backdrop-filter: blur(8px);
}

.auth-play svg {
  width: 38px;
  height: 38px;
  color: #fff;
}

.auth-play i {
  position: absolute;
  inset: 3px;
  border: 1px solid rgb(255 255 255 / 13%);
  border-radius: 50%;
  animation: auth-pulse 3.2s ease-in-out infinite;
}

.auth-play i:last-child {
  inset: -9px;
  opacity: .55;
  animation-delay: 1.1s;
}

@keyframes auth-pulse {
  0%, 100% { opacity: .32; transform: scale(.94); }
  50% { opacity: .76; transform: scale(1.04); }
}

.auth-panel-copy {
  position: absolute;
  z-index: 5;
  right: 44px;
  bottom: 64px;
  left: 44px;
  text-align: center;
  transition:
    opacity calc(var(--auth-time) * .58) ease,
    transform var(--auth-time) var(--auth-ease),
    filter calc(var(--auth-time) * .52) ease;
}

.auth-panel-copy small {
  display: inline-block;
  margin-bottom: 8px;
  color: rgb(255 255 255 / 66%);
  font-size: .66rem;
  font-weight: 700;
}

.auth-panel-copy h2 {
  margin: 0 0 10px;
  color: #fff;
  font-size: 2rem;
  font-weight: 900;
  letter-spacing: -.055em;
}

.auth-panel-copy p {
  min-height: 50px;
  margin: 0 auto 20px;
  color: rgb(255 255 255 / 78%);
  font-size: .78rem;
  line-height: 1.9;
}

.auth-panel-copy button {
  display: flex;
  width: 142px;
  height: 43px;
  margin-inline: auto;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid rgb(255 255 255 / 46%);
  border-radius: 12px;
  background: rgb(var(--palette-void-rgb) / 18%);
  color: #fff;
  font-size: .76rem;
  font-weight: 800;
  backdrop-filter: blur(8px);
}

.auth-panel-copy button:hover {
  border-color: rgb(255 255 255 / 82%);
  background: rgb(255 255 255 / 11%);
  transform: translateY(-2px);
}

.auth-panel-copy button :deep(svg) {
  width: 18px;
  height: 18px;
}

.auth-panel-copy--register {
  opacity: 1;
}

.auth-panel-copy--login {
  opacity: 0;
  pointer-events: none;
  filter: blur(3px);
  transform: translateX(-52px);
}

.is-register .auth-panel-copy--register {
  opacity: 0;
  pointer-events: none;
  filter: blur(3px);
  transform: translateX(52px);
}

.is-register .auth-panel-copy--login {
  opacity: 1;
  pointer-events: auto;
  filter: none;
  transform: translateX(0);
}

:global(html[data-theme="light"] .auth-portal) {
  border-color: var(--theme-border);
  background: var(--theme-bg-surface);
  box-shadow: 0 28px 70px rgb(23 50 38 / 14%), 0 8px 24px rgb(23 50 38 / 7%);
}

:global(html[data-theme="light"] .auth-portal::before) {
  background: linear-gradient(120deg, rgb(255 255 255 / 72%), transparent 22% 78%, rgb(23 107 80 / 3%));
}

:global(html[data-theme="light"] .auth-field input) {
  border-color: var(--theme-border-strong);
  background: var(--theme-control-bg);
  box-shadow: 0 1px 0 rgb(23 50 38 / 3%);
}

:global(html[data-theme="light"] .auth-field input:hover) {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 38%, var(--theme-border));
  background: var(--theme-bg-surface);
}

:global(html[data-theme="light"] .auth-field input:focus) {
  border-color: var(--theme-accent-primary);
  background: var(--theme-bg-surface);
  box-shadow: 0 0 0 4px var(--theme-focus-ring);
}

:global(html[data-theme="light"] .password-toggle:hover),
:global(html[data-theme="light"] .password-toggle:focus-visible) {
  background: var(--theme-surface-hover);
}

:global(html[data-theme="light"] .auth-check > span:first-of-type) {
  border-color: var(--theme-border-strong);
  background: var(--theme-bg-surface);
}

:global(html[data-theme="light"] .auth-check input:checked + span) :deep(svg) {
  color: var(--theme-on-accent);
}

:global(html[data-theme="light"] .auth-divider::before),
:global(html[data-theme="light"] .auth-divider::after) {
  background: linear-gradient(90deg, transparent, var(--theme-border-strong));
}

:global(html[data-theme="light"] .auth-divider::after) {
  background: linear-gradient(90deg, var(--theme-border-strong), transparent);
}

:global(html[data-theme="light"] .auth-google) {
  border-color: var(--theme-border-strong);
  background: var(--theme-bg-surface);
  box-shadow: 0 5px 16px rgb(23 50 38 / 5%);
}

:global(html[data-theme="light"] .auth-google:hover) {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 36%, var(--theme-border));
  background: var(--theme-surface-selected);
}

@media (max-width: 720px) {
  .auth-portal {
    width: min(100%, 460px);
    height: 730px;
    border-radius: 24px;
    transition: height var(--auth-time) var(--auth-ease);
  }

  .auth-portal.is-register {
    height: 845px;
  }

  .auth-cinema-panel,
  .is-register .auth-cinema-panel {
    top: 0;
    left: 0;
    width: 100%;
    height: 190px;
    border-radius: 24px 24px 22px 22px;
    box-shadow: 0 16px 38px rgb(0 0 0 / 28%);
    transform: none;
  }

  .auth-cinema-panel::before {
    top: -285px;
    left: -45px;
  }

  .auth-cinema-panel::after {
    right: -25px;
    bottom: -140px;
  }

  .auth-cinema-panel__light {
    top: -130px;
    right: 42%;
    height: 330px;
  }

  .auth-film-strip {
    top: 12px;
    left: -42px;
  }

  .auth-play {
    top: 31px;
    right: 29px;
    left: auto;
    width: 74px;
    height: 74px;
    transform: none;
  }

  .auth-play > span {
    inset: 13px;
  }

  .auth-play svg {
    width: 29px;
    height: 29px;
  }

  .auth-panel-copy {
    top: 29px;
    right: 120px;
    bottom: auto;
    left: 28px;
    text-align: right;
  }

  .auth-panel-copy small {
    margin-bottom: 3px;
    font-size: .6rem;
  }

  .auth-panel-copy h2 {
    margin-bottom: 3px;
    font-size: 1.4rem;
  }

  .auth-panel-copy p {
    min-height: auto;
    margin: 0;
    font-size: .67rem;
    line-height: 1.7;
  }

  .auth-panel-copy button {
    width: auto;
    height: auto;
    margin: 7px 0 0;
    padding: 0;
    justify-content: flex-start;
    border: 0;
    background: transparent;
    box-shadow: none;
    font-size: .68rem;
    backdrop-filter: none;
  }

  .auth-form,
  .auth-form--login,
  .auth-form--register {
    top: 190px;
    right: 0;
    left: 0;
    width: 100%;
    height: calc(100% - 190px);
  }

  .auth-form__inner,
  .auth-form__inner--register {
    padding: 25px clamp(24px, 8vw, 42px) 19px;
    justify-content: flex-start;
  }

  .auth-heading {
    margin-bottom: 19px;
    text-align: center;
  }

  .auth-heading--compact {
    margin-bottom: 13px;
  }

  .auth-heading > span {
    display: none;
  }

  .auth-heading h1,
  .auth-heading h2 {
    font-size: 1.62rem;
  }

  .auth-field input,
  .auth-fields--compact .auth-field input {
    height: 48px;
  }

  .auth-fields,
  .auth-fields--compact {
    gap: 9px;
  }

  .auth-terms {
    margin-block: 12px;
  }

  .auth-mobile-switch {
    display: block;
  }
}

@media (max-width: 390px) {
  .auth-portal {
    height: 722px;
  }

  .auth-portal.is-register {
    height: 836px;
  }

  .auth-cinema-panel,
  .is-register .auth-cinema-panel {
    height: 180px;
  }

  .auth-form,
  .auth-form--login,
  .auth-form--register {
    top: 180px;
    height: calc(100% - 180px);
  }

  .auth-panel-copy {
    top: 27px;
    right: 103px;
    left: 18px;
  }

  .auth-play {
    right: 17px;
  }

  .auth-panel-copy h2 {
    font-size: 1.24rem;
  }

  .auth-panel-copy p {
    font-size: .62rem;
  }

  .auth-form__inner,
  .auth-form__inner--register {
    padding-inline: 20px;
  }

  .auth-options,
  .auth-check {
    font-size: .63rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-portal {
    --auth-time: 1ms;
  }

  .auth-portal *,
  .auth-portal *::before,
  .auth-portal *::after {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
}
</style>
