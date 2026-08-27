<template>
  <!-- Avoid overflow-x-clip on sticky ancestors — it breaks sticky header/tabs. -->
  <div class="cinematic-app flex min-h-dvh flex-col">
    <AppHeader />
    <main
      id="main-content"
      tabindex="-1"
      class="min-h-[calc(100dvh-var(--header-height))] min-w-0 flex-1"
    >
      <span id="page-top-sentinel" class="pointer-events-none absolute h-px w-px" aria-hidden="true" />
      <slot />
    </main>
    <AppFooter />
    <ScrollToTop />
    <TelegramWelcomeModal />
  </div>
</template>

<style scoped>
.cinematic-app {
  padding-bottom: calc(var(--mobile-bottom-nav-height) + env(safe-area-inset-bottom, 0px));
}

@media (min-width: 1024px) {
  .cinematic-app {
    padding-bottom: 0;
  }
}
</style>
