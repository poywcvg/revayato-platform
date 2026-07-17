<template>
  <div class="cinematic-app relative min-h-dvh overflow-x-clip text-slate-50">
    <a
      href="#player-content"
      class="fixed start-4 top-4 z-[120] -translate-y-20 rounded-xl bg-primary-500 px-4 py-3 text-sm font-black text-night-950 transition focus:translate-y-0"
    >
      رفتن به پخش‌کننده
    </a>
    <div class="pointer-events-none fixed inset-0" aria-hidden="true">
      <div class="ambient-orb absolute -right-40 -top-52 h-[32rem] w-[32rem] rounded-full" />
      <div class="ambient-orb ambient-orb--crimson absolute -bottom-64 -left-52 h-[38rem] w-[38rem] rounded-full" />
    </div>
    <main id="player-content" class="relative min-h-dvh">
      <slot />
    </main>
  </div>
</template>
