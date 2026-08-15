export default defineNuxtRouteMiddleware(async (to) => {
  const authStore = useAuthStore()
  await authStore.initialize()
  if (!authStore.isAuthenticated) {
    return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
  }
  if (!authStore.user) {
    try {
      await authStore.fetchMe()
    } catch {
      throw createError({ statusCode: 503, message: 'بررسی دسترسی ادمین ممکن نشد.' })
    }
  }
  if (!authStore.user?.is_staff) {
    throw createError({ statusCode: 403, message: 'این بخش فقط برای اعضای تیم محتواست.' })
  }
})
