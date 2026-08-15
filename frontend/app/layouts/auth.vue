<script setup lang="ts">
useHead({
  htmlAttrs: { class: 'auth-page-root' },
  bodyAttrs: { class: 'auth-page-body' },
})
</script>

<template>
  <div class="auth-layout">
    <a href="#main-content" class="auth-skip-link">پرش به فرم</a>

    <header class="auth-layout__header">
      <NuxtLink to="/" class="auth-brand" aria-label="روایتو، صفحه اصلی">
        <span class="auth-brand__mark" aria-hidden="true">
          <img src="/assets/brand/logo.svg" alt="" width="45" height="45" decoding="async">
        </span>
        <span>
          <strong>روایتو</strong>
          <small>هر قاب، یک روایت</small>
        </span>
      </NuxtLink>

      <NuxtLink to="/" class="auth-home-link">
        <CinematicIcon name="arrow-right" />
        بازگشت به خانه
      </NuxtLink>
    </header>

    <main id="main-content" tabindex="-1" class="auth-layout__main">
      <slot />
    </main>

    <p class="auth-security-note">
      <CinematicIcon name="shield-check" />
      اطلاعات شما با استانداردهای امنیتی محافظت می‌شود
    </p>
  </div>
</template>

<style scoped>
:global(html.auth-page-root) {
  scrollbar-gutter: auto;
  background: var(--theme-bg-main);
}

:global(body.auth-page-body) {
  background: var(--theme-bg-main);
}

.auth-layout {
  position: relative;
  display: grid;
  min-height: 100dvh;
  overflow-x: clip;
  grid-template-rows: auto 1fr auto;
  background: var(--theme-bg-main);
  color: var(--theme-text-primary);
  isolation: isolate;
}

.auth-layout::before {
  position: fixed;
  z-index: -3;
  inset: -24px;
  background:
    radial-gradient(circle at 50% 48%, rgb(var(--palette-void-rgb) / 36%) 0 18%, rgb(var(--palette-void-rgb) / 82%) 70%),
    linear-gradient(180deg, rgb(var(--palette-void-rgb) / 58%), rgb(var(--palette-void-rgb) / 88%)),
    url("/assets/auth/cinematic-posters.png") center / cover no-repeat;
  content: "";
  filter: saturate(.72) contrast(1.06);
  transform: scale(1.03);
}

.auth-layout::after {
  position: fixed;
  z-index: -2;
  top: 7%;
  right: -170px;
  width: 390px;
  height: 390px;
  border-radius: 50%;
  background: var(--palette-mid);
  content: "";
  filter: blur(100px);
  opacity: .22;
}

.auth-layout__header {
  position: relative;
  z-index: 30;
  display: flex;
  width: 100%;
  max-width: 1440px;
  margin-inline: auto;
  padding: 28px clamp(22px, 4vw, 52px) 10px;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.auth-brand {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  color: var(--theme-text-primary);
}

.auth-brand__mark {
  display: grid;
  width: 45px;
  height: 45px;
  place-items: center;
  overflow: hidden;
}

.auth-brand__mark img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.auth-brand > span:last-child {
  display: grid;
  gap: 1px;
}

.auth-brand strong {
  font-size: 1.22rem;
  font-weight: 900;
  letter-spacing: -.035em;
}

.auth-brand small {
  color: var(--theme-text-muted);
  font-size: .65rem;
}

.auth-home-link {
  display: flex;
  min-height: 44px;
  padding: 0 14px;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--theme-border);
  border-radius: 12px;
  background: rgb(255 255 255 / 4%);
  color: var(--theme-text-secondary);
  font-size: .72rem;
  font-weight: 700;
  backdrop-filter: blur(12px);
}

.auth-home-link:hover {
  border-color: rgb(var(--palette-sand-rgb) / 28%);
  background: var(--theme-accent-primary-soft);
  color: var(--theme-text-primary);
  transform: translateY(-2px);
}

.auth-home-link :deep(svg) {
  width: 16px;
  height: 16px;
}

.auth-layout__main {
  display: grid;
  width: 100%;
  padding: 18px 22px;
  place-items: center;
}

.auth-layout__main :deep(.page-section) {
  width: min(920px, 100%);
}

.auth-layout__main :deep(.auth-shell) {
  max-width: 920px;
  margin-inline: auto;
}

.auth-security-note {
  display: flex;
  margin: 0 auto;
  padding: 8px 20px 22px;
  align-items: center;
  gap: 7px;
  color: var(--theme-text-muted);
  font-size: .66rem;
}

.auth-security-note :deep(svg) {
  width: 14px;
  height: 14px;
}

.auth-skip-link {
  position: fixed;
  z-index: 100;
  top: 8px;
  right: 16px;
  padding: 8px 14px;
  border-radius: 10px;
  background: var(--palette-mid);
  color: var(--theme-text-primary);
  font-size: .75rem;
  font-weight: 800;
  transform: translateY(-80px);
  transition: transform 180ms ease;
}

.auth-skip-link:focus {
  transform: translateY(0);
}

:global(html[data-theme="light"] .auth-layout) {
  background:
    radial-gradient(circle at 88% 8%, rgb(23 107 80 / 8%), transparent 24rem),
    var(--theme-bg-main);
}

:global(html[data-theme="light"] .auth-layout::before) {
  background:
    linear-gradient(180deg, rgb(244 247 245 / 82%), rgb(244 247 245 / 94%)),
    url("/assets/auth/cinematic-posters.png") center / cover no-repeat;
  filter: saturate(.55) contrast(.92);
}

:global(html[data-theme="light"] .auth-layout::after) {
  background: var(--theme-accent-primary);
  opacity: .08;
}

:global(html[data-theme="light"] .auth-layout__header) {
  border-bottom: 1px solid color-mix(in srgb, var(--theme-border) 75%, transparent);
  background: color-mix(in srgb, var(--theme-bg-surface) 72%, transparent);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  backdrop-filter: blur(16px) saturate(120%);
}

:global(html[data-theme="light"] .auth-home-link) {
  border-color: var(--theme-border-strong);
  background: color-mix(in srgb, var(--theme-bg-surface) 90%, transparent);
  box-shadow: 0 5px 16px rgb(23 50 38 / 6%);
}

:global(html[data-theme="light"] .auth-skip-link) {
  background: var(--theme-accent-primary);
  color: var(--theme-on-accent);
}

@media (max-width: 720px) {
  .auth-layout {
    display: block;
    min-height: 100dvh;
  }

  .auth-layout__header {
    padding: 20px 18px 9px;
  }

  .auth-brand__mark {
    width: 41px;
    height: 41px;
  }

  .auth-brand strong {
    font-size: 1.08rem;
  }

  .auth-home-link {
    width: 44px;
    padding: 0;
    justify-content: center;
    font-size: 0;
  }

  .auth-home-link :deep(svg) {
    width: 18px;
    height: 18px;
  }

  .auth-layout__main {
    padding: 12px 10px 18px;
  }

  .auth-security-note {
    justify-content: center;
    padding-bottom: 25px;
    text-align: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-layout *,
  .auth-layout *::before,
  .auth-layout *::after {
    scroll-behavior: auto !important;
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
}
</style>
