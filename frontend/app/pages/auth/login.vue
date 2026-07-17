<script setup lang="ts">
import type { AppErrorDetails } from '~/types'

definePageMeta({ layout: 'auth', middleware: 'guest' })

const authStore = useAuthStore()
const notifications = useNotifications()
const route = useRoute()
const email = ref('')
const password = ref('')
const error = ref<AppErrorDetails | null>(null)
const redirectPath = computed(() => {
  const value = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  return value.startsWith('/') && !value.startsWith('//') ? value : '/'
})

async function submit() {
  error.value = null
  try {
    const user = await authStore.login(email.value, password.value)
    notifications.success('خوش آمدی', `${user.username}، ورود با موفقیت انجام شد.`)
    await navigateTo(redirectPath.value)
  } catch (cause) {
    error.value = getAppError(cause, 'ورود به حساب انجام نشد.')
    notifications.error(error.value.title, error.value.message)
  }
}

useSeoMeta({ title: 'ورود' })
</script>

<template>
  <AuthShell title="خوش برگشتی" eyebrow="ورود امن" description="وارد شو تا ادامه تماشا و فهرست شخصی تو روی همه دستگاه‌ها در دسترس باشد." icon="login">
    <h2 class="text-2xl font-black text-ink">ورود به حساب</h2>
    <p class="mt-2 text-sm leading-7 text-muted">ایمیل و رمز عبورت را وارد کن.</p>
    <form class="mt-7 space-y-4" :aria-busy="authStore.pending" @submit.prevent="submit">
      <div>
        <label class="mb-1.5 block text-sm font-bold text-secondary" for="email">ایمیل</label>
        <input id="email" v-model="email" type="email" inputmode="email" autocomplete="email" required class="ui-field px-4 text-sm" placeholder="name@example.com">
      </div>
      <div>
        <AuthPasswordField id="password" v-model="password" autocomplete="current-password" />
        <div class="mt-1 text-left"><NuxtLink to="/auth/forgot-password" class="inline-flex min-h-8 items-center rounded-lg px-1 text-xs font-black text-primary-300 hover:text-primary-200">رمز را فراموش کرده‌ام</NuxtLink></div>
      </div>

      <UiErrorAlert v-if="error" :error="error" @close="error = null" />

      <button type="submit" :disabled="authStore.pending" class="ui-primary-button w-full">
        <span v-if="authStore.pending" class="size-4 animate-spin rounded-full border-2 border-night-950/30 border-t-night-950" aria-hidden="true" />
        {{ authStore.pending ? 'در حال ورود…' : 'ورود' }}
      </button>
    </form>

    <p class="mt-5 text-center text-sm text-secondary">
      حساب کاربری نداری؟
      <NuxtLink :to="{ path: '/auth/register', query: route.query.redirect ? { redirect: redirectPath } : {} }" class="font-black text-primary-300 hover:text-primary-200">ساخت حساب</NuxtLink>
    </p>
  </AuthShell>
</template>
