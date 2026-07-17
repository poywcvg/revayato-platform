<script setup lang="ts">
import type { AppErrorDetails } from '~/types'

definePageMeta({ layout: 'auth', middleware: 'guest' })

const { api } = useApi()
const notifications = useNotifications()
const email = ref('')
const pending = ref(false)
const sent = ref(false)
const error = ref<AppErrorDetails | null>(null)

async function submit() {
  pending.value = true
  error.value = null
  try {
    await api('/auth/password-reset/', { method: 'POST', body: { email: email.value.trim().toLowerCase() } })
    sent.value = true
    notifications.success('درخواست ثبت شد', 'اگر این ایمیل حساب داشته باشد، لینک بازیابی برای آن فرستاده می‌شود.')
  } catch (cause) {
    error.value = getAppError(cause, 'فرستادن درخواست بازیابی ممکن نشد.')
  } finally {
    pending.value = false
  }
}

useSeoMeta({ title: 'بازیابی رمز عبور' })
</script>

<template>
  <AuthShell title="دوباره وارد حسابت شو" eyebrow="بازیابی رمز عبور" description="ایمیل حسابت را وارد کن تا راه ساخت یک رمز تازه برایت فرستاده شود." icon="lock">
    <div v-if="sent" class="text-center">
      <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-success/10 text-success ring-1 ring-success/20"><CinematicIcon name="check-circle" class="size-7" /></span>
      <h2 class="mt-5 text-2xl font-black text-ink">ایمیلت را بررسی کن</h2>
      <p class="mt-3 text-sm leading-7 text-secondary">اگر <span dir="ltr" class="font-latin text-ink">{{ email }}</span> در سایت ثبت شده باشد، لینک بازیابی برای آن فرستاده می‌شود. پوشه هرزنامه را هم ببین.</p>
      <button type="button" class="ui-secondary-button mt-6 w-full" @click="sent = false">فرستادن دوباره</button>
      <NuxtLink to="/auth/login" class="ui-ghost-button mt-2 w-full">بازگشت به ورود</NuxtLink>
    </div>
    <template v-else>
      <h2 class="text-2xl font-black text-ink">رمزت را فراموش کرده‌ای؟</h2>
      <p class="mt-2 text-sm leading-7 text-muted">نگران نباش؛ ایمیل حسابت را وارد کن.</p>
      <form class="mt-7 space-y-4" :aria-busy="pending" @submit.prevent="submit">
        <div><label class="mb-1.5 block text-sm font-bold text-secondary" for="email">ایمیل</label><input id="email" v-model="email" type="email" inputmode="email" autocomplete="email" required class="ui-field px-4 text-sm" placeholder="name@example.com"></div>
        <UiErrorAlert v-if="error" :error="error" @close="error = null" />
        <button type="submit" :disabled="pending" class="ui-primary-button w-full">{{ pending ? 'در حال فرستادن…' : 'فرستادن لینک بازیابی' }}</button>
      </form>
      <NuxtLink to="/auth/login" class="ui-ghost-button mt-3 w-full"><CinematicIcon name="arrow-right" class="size-4" />بازگشت به ورود</NuxtLink>
    </template>
  </AuthShell>
</template>
