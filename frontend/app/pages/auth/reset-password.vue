<script setup lang="ts">
import type { AppErrorDetails } from '~/types'

definePageMeta({ layout: 'auth', middleware: 'guest' })

const route = useRoute()
const { api } = useApi()
const notifications = useNotifications()
const password = ref('')
const confirmation = ref('')
const pending = ref(false)
const done = ref(false)
const error = ref<AppErrorDetails | null>(null)
const uid = computed(() => typeof route.query.uid === 'string' ? route.query.uid : '')
const token = computed(() => typeof route.query.token === 'string' ? route.query.token : '')
const validLink = computed(() => Boolean(uid.value && token.value))

async function submit() {
  error.value = null
  if (password.value !== confirmation.value) {
    error.value = { title: 'رمزها یکسان نیستند', message: 'رمز عبور و تکرار آن باید دقیقاً یکسان باشند.', hint: 'هر دو بخش را دوباره وارد کن.', fields: [] }
    return
  }
  pending.value = true
  try {
    await api('/auth/password-reset/confirm/', { method: 'POST', body: { uid: uid.value, token: token.value, password: password.value } })
    done.value = true
    notifications.success('رمز تغییر کرد', 'اکنون می‌توانی با رمز تازه وارد حسابت شوی.')
  } catch (cause) {
    error.value = getAppError(cause, 'تغییر رمز عبور انجام نشد.')
  } finally {
    pending.value = false
  }
}

useSeoMeta({ title: 'ساخت رمز تازه' })
</script>

<template>
  <AuthShell title="یک رمز تازه بساز" eyebrow="امنیت حساب" description="رمزی انتخاب کن که حدس‌زدن آن آسان نباشد و جای دیگری از آن استفاده نکرده باشی." icon="shield-check">
    <div v-if="done" class="text-center"><span class="mx-auto grid size-14 place-items-center rounded-2xl bg-success/10 text-success"><CinematicIcon name="check-circle" class="size-7" /></span><h2 class="mt-5 text-2xl font-black text-ink">رمز عبور تغییر کرد</h2><p class="mt-2 text-sm leading-7 text-secondary">با رمز تازه وارد حسابت شو.</p><NuxtLink to="/auth/login" class="ui-primary-button mt-6 w-full">رفتن به صفحه ورود</NuxtLink></div>
    <div v-else-if="!validLink" class="text-center"><span class="mx-auto grid size-14 place-items-center rounded-2xl bg-error/10 text-error"><CinematicIcon name="alert-triangle" class="size-7" /></span><h2 class="mt-5 text-2xl font-black text-ink">لینک کامل نیست</h2><p class="mt-2 text-sm leading-7 text-secondary">این لینک بازیابی قابل استفاده نیست. یک لینک تازه بگیر.</p><NuxtLink to="/auth/forgot-password" class="ui-primary-button mt-6 w-full">گرفتن لینک تازه</NuxtLink></div>
    <template v-else>
      <h2 class="text-2xl font-black text-ink">رمز عبور تازه</h2>
      <p class="mt-2 text-sm leading-7 text-muted">رمز تازه را دو بار وارد کن.</p>
      <form class="mt-7 space-y-4" :aria-busy="pending" @submit.prevent="submit">
        <AuthPasswordField id="password" v-model="password" autocomplete="new-password" show-strength />
        <AuthPasswordField id="password-confirm" v-model="confirmation" label="تکرار رمز عبور" autocomplete="new-password" />
        <UiErrorAlert v-if="error" :error="error" @close="error = null" />
        <button type="submit" :disabled="pending" class="ui-primary-button w-full">{{ pending ? 'در حال تغییر…' : 'تغییر رمز عبور' }}</button>
      </form>
    </template>
  </AuthShell>
</template>
