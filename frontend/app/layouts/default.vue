<script setup lang="ts">
const route = useRoute()
const cinematic = computed(() => route.path === '/' || route.path.startsWith('/watch'))
</script>

<template>
  <div class="cinematic-app flex min-h-dvh flex-col overflow-x-clip">
    <AppHeader />
    <div class="mx-auto flex w-full max-w-[1600px] flex-1">
      <main id="main-content" class="min-h-[calc(100dvh-132px)] min-w-0 flex-1 overflow-x-clip md:min-h-[calc(100dvh-68px)]" :class="cinematic ? 'bg-transparent' : 'app-light-page'">
        <span id="page-top-sentinel" class="pointer-events-none absolute h-px w-px" aria-hidden="true" />
        <slot />
      </main>
    </div>
    <AppFooter />
    <MobileBottomNav />
    <ScrollToTop />
  </div>
</template>
