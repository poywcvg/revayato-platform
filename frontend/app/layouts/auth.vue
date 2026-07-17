<template>
  <div class="cinematic-app flex min-h-dvh flex-col overflow-x-clip text-ink">
    <a href="#main-content" class="absolute right-4 top-2 z-50 -translate-y-20 rounded-xl bg-primary-500 px-4 py-2 text-sm font-black text-night-950 transition-transform focus:translate-y-0">پرش به فرم</a>
    <header class="border-b border-line bg-canvas-soft">
      <div class="page-shell flex h-[68px] items-center justify-between gap-4">
        <AppLogo :compact-on-mobile="false" />
        <NuxtLink to="/" class="ui-ghost-button min-h-11 px-3 text-xs sm:text-sm">
          <CinematicIcon name="arrow-right" class="size-4" />
          بازگشت به خانه
        </NuxtLink>
      </div>
    </header>
    <main id="main-content" class="min-h-0 flex-1">
      <slot />
    </main>
  </div>
</template>
