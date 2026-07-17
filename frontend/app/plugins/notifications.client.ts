export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.hook('app:mounted', () => useNotifications().hydrate())
})
