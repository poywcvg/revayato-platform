export default defineNuxtRouteMiddleware(async (to) => {
  const authStore = useAuthStore()
  await authStore.initialize()
  if (!authStore.user) return
  const redirect = typeof to.query.redirect === 'string' && to.query.redirect.startsWith('/') && !to.query.redirect.startsWith('//')
    ? to.query.redirect
    : '/profile'
  return navigateTo(redirect)
})
