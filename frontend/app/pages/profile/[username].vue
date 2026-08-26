<script setup lang="ts">
const route = useRoute()
const authStore = useAuthStore()

const username = String(route.params.username || '')

// The signed-in user's own profile lives at /profile; redirect to avoid a
// duplicate "coming soon" page for yourself.
if (username && username === authStore.user?.username) {
  await navigateTo('/profile', { redirectCode: 301, replace: true })
}

useSeoMeta({ title: username ? `پروفایل ${username}` : 'پروفایل' })
</script>

<template>
  <div class="cinema-page page-section">
    <PageHero
      :title="username ? `پروفایل ${username}` : 'پروفایل کاربر'"
      eyebrow="جامعه روایتو"
      description="صفحه عمومی کاربران به‌زودی میزبان فهرست‌های منتخب و نظرهای سینمایی خواهد بود."
      icon="user"
    />
    <EmptyState
      title="این پرده هنوز آماده نمایش نیست"
      description="نمایش عمومی پروفایل، فهرست‌های منتخب و فعالیت کاربران در نسخه بعدی فعال می‌شود."
      icon="users"
      :action-label="authStore.isAuthenticated ? 'رفتن به پروفایل من' : 'بازگشت به خانه'"
      :action-href="authStore.isAuthenticated ? '/profile' : '/'"
    />
  </div>
</template>
