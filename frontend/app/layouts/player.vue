<template>
  <div
    class="player-layout theme-media-dark relative overflow-hidden bg-black text-slate-50"
    dir="rtl"
    lang="fa"
  >
    <a
      href="#player-content"
      class="fixed start-4 top-4 z-[120] -translate-y-20 rounded-xl bg-primary-500 px-4 py-3 text-sm font-black text-night-950 transition focus:translate-y-0"
    >
      رفتن به پخش‌کننده
    </a>
    <main id="player-content" tabindex="-1" class="player-layout__main relative w-full">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.player-layout,
.player-layout__main {
  min-height: 100vh;
  min-height: 100dvh;
  min-height: 100svh;
}
</style>
