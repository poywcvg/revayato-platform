<script setup lang="ts">
import type { AppErrorDetails } from "~/types";

definePageMeta({ layout: "auth", middleware: "guest" });

const authStore = useAuthStore();
const notifications = useNotifications();
const route = useRoute();
const email = ref("");
const username = ref("");
const password = ref("");
const error = ref<AppErrorDetails | null>(null);
const redirectPath = computed(() => {
  const value =
    typeof route.query.redirect === "string" ? route.query.redirect : "/";
  return value.startsWith("/") && !value.startsWith("//") ? value : "/";
});

async function submit() {
  error.value = null;
  try {
    const user = await authStore.register(
      email.value,
      username.value,
      password.value,
    );
    notifications.success(
      "حساب ساخته شد",
      `${user.username}، حالا می‌توانی فهرست شخصی‌ات را بسازی.`,
      { inbox: true, href: "/profile" },
    );
    await navigateTo(redirectPath.value);
  } catch (cause) {
    error.value = getAppError(cause, "ساخت حساب انجام نشد.");
    notifications.error(error.value.title, error.value.message);
  }
}

useSeoMeta({ title: "ساخت حساب" });
</script>

<template>
  <AuthShell
    title="سینمای خودت را بساز"
    eyebrow="عضویت سریع"
    description="با یک حساب امن، ادامه تماشا و انتخاب‌های تو همیشه همراهت می‌ماند."
    icon="user-plus"
  >
    <h2 class="text-2xl font-black text-ink">ساخت حساب کاربری</h2>
    <p class="mt-2 text-sm leading-7 text-muted">
      سه بخش زیر را کامل کن؛ کمتر از یک دقیقه زمان می‌برد.
    </p>
    <form
      class="mt-7 space-y-4"
      :aria-busy="authStore.pending"
      @submit.prevent="submit"
    >
      <div>
        <label
          class="mb-1.5 block text-sm font-bold text-secondary"
          for="username"
          >نام کاربری</label
        >
        <input
          id="username"
          v-model="username"
          type="text"
          autocomplete="username"
          required
          minlength="3"
          maxlength="150"
          class="ui-field px-4 text-sm"
          placeholder="بدون فاصله، حداقل ۳ کاراکتر"
        >
      </div>
      <div>
        <label class="mb-1.5 block text-sm font-bold text-secondary" for="email"
          >ایمیل</label
        >
        <input
          id="email"
          v-model="email"
          type="email"
          inputmode="email"
          autocomplete="email"
          required
          class="ui-field px-4 text-sm"
          placeholder="name@example.com"
        >
      </div>
      <AuthPasswordField
        id="password"
        v-model="password"
        autocomplete="new-password"
        show-strength
      />

      <UiErrorAlert v-if="error" :error="error" @close="error = null" />

      <button
        type="submit"
        :disabled="authStore.pending"
        class="ui-primary-button w-full"
      >
        <span
          v-if="authStore.pending"
          class="size-4 animate-spin rounded-full border-2 border-night-950/30 border-t-night-950"
          aria-hidden="true"
        />
        {{ authStore.pending ? "در حال ساخت حساب…" : "ساخت حساب" }}
      </button>
    </form>

    <p class="mt-5 text-center text-sm text-secondary">
      قبلاً حساب ساخته‌ای؟
      <NuxtLink
        :to="{
          path: '/auth/login',
          query: route.query.redirect ? { redirect: redirectPath } : {},
        }"
        class="font-black text-primary-300 hover:text-primary-200"
        >ورود</NuxtLink
      >
    </p>
  </AuthShell>
</template>
