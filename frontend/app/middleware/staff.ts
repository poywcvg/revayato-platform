export default defineNuxtRouteMiddleware(async (to) => {
  const authStore = useAuthStore()
  await authStore.initialize()
  if (!authStore.isAuthenticated) {
    return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
  }
  if (!authStore.user) {
    try {
      await authStore.fetchMe()
    }
    catch (error) {
      const status = (error as { status?: number, statusCode?: number, response?: { status?: number } })?.status
        || (error as { statusCode?: number })?.statusCode
        || (error as { response?: { status?: number } })?.response?.status
        || 0
      // نشست تمام‌شده باید به لاگین برگردد، نه اینکه صفحه با خطای ۵۰۳ قفل شود.
      if (status === 401) {
        return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
      }
      throw createError({ statusCode: 503, message: 'بررسی دسترسی ادمین ممکن نشد.' })
    }
  }
  if (!authStore.user?.is_staff) {
    throw createError({ statusCode: 403, message: 'این بخش فقط برای اعضای تیم محتواست.' })
  }
})
