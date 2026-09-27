<script setup lang="ts">
// Public profiles now live under /u/[username]. This legacy route redirects
// there so old links (and the signed-in user's own /profile) keep working.
const route = useRoute()
const authStore = useAuthStore()
const username = String(route.params.username || '')

if (username && username === authStore.user?.username) {
  await navigateTo('/profile', { redirectCode: 301, replace: true })
} else if (username) {
  await navigateTo(`/u/${username}`, { redirectCode: 301, replace: true })
} else {
  await navigateTo('/', { replace: true })
}
</script>

<template>
  <div class="cinema-page page-section grid place-items-center py-24">
    <LoadingSpinnerA />
  </div>
</template>
