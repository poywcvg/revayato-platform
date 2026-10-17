<template>
  <div class="route-loader" aria-hidden="true">
    <div class="route-loader__card">
      <span class="route-loader__reel">
        <span class="route-loader__ring" />
        <span class="route-loader__ring route-loader__ring--inner" />
        <img class="route-loader__mark" src="/favicon.svg?v=2" alt="" width="30" height="30" decoding="async">
      </span>
      <span class="route-loader__label">
        در حال بارگذاری
        <span class="route-loader__dots"><i /><i /><i /></span>
      </span>
    </div>
  </div>
</template>

<style scoped>
/*
 * Shown only while html[data-page-navigating] is set (navigation-ux plugin).
 * The 180ms entry delay keeps instant (cached/prefetched) navigations clean:
 * the card appears only when the user would otherwise stare at a frozen page.
 * Leaving is immediate. Only opacity/transform animate (compositor-only).
 */
.route-loader {
  --rl-mint: var(--theme-accent-primary, #b0e4cc);
  --rl-mint-light: var(--theme-accent-primary-hover, #c8efdc);
  --rl-mint-deep: var(--theme-accent-crimson, #408a71);
  position: fixed;
  inset: 0;
  z-index: 9997;
  display: grid;
  place-items: center;
  pointer-events: none;
  visibility: hidden;
  opacity: 0;
  background: radial-gradient(circle at 50% 46%, rgb(0 0 0 / 22%), transparent 58%);
  transition: opacity 90ms ease, visibility 0s linear 90ms;
}

.route-loader__card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: .8rem;
  padding: 1.25rem 1.6rem 1rem;
  border: 1px solid color-mix(in srgb, var(--rl-mint) 22%, transparent);
  border-radius: 1.25rem;
  background: color-mix(in srgb, var(--theme-bg-elevated, #141414) 97%, transparent);
  box-shadow:
    0 0 0 1px rgb(255 255 255 / 4%) inset;
  transform: translate3d(0, 10px, 0) scale(.94);
  transition: transform 90ms ease;
}

.route-loader__reel {
  position: relative;
  display: grid;
  width: 4rem;
  height: 4rem;
  place-items: center;
}

.route-loader__ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(from 0deg, transparent 0 18%, var(--rl-mint-deep) 40%, var(--rl-mint) 72%, var(--rl-mint-light) 88%, transparent 90%);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 3px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 3px));
  filter: none;
}

.route-loader__ring--inner {
  inset: 7px;
  opacity: .55;
  background: conic-gradient(from 180deg, transparent 0 30%, var(--rl-mint-light) 62%, transparent 64%);
  filter: none;
}

.route-loader__mark {
  width: 1.9rem;
  height: 1.9rem;
  border-radius: .55rem;
}

.route-loader__label {
  display: inline-flex;
  align-items: baseline;
  gap: .3rem;
  color: var(--theme-text-primary, #fff);
  font-size: .8rem;
  font-weight: 700;
  letter-spacing: 0;
  white-space: nowrap;
}

.route-loader__dots {
  display: inline-flex;
  gap: 3px;
}

.route-loader__dots i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--rl-mint);
  opacity: .3;
}

html[data-page-navigating] .route-loader {
  visibility: visible;
  opacity: 1;
  transition: opacity 160ms ease 180ms, visibility 0s linear 180ms;
}

html[data-page-navigating] .route-loader__card {
  transform: none;
  transition: transform 260ms cubic-bezier(.22, 1, .36, 1) 180ms;
}

/* Animations run only while visible, so an idle loader costs nothing. */
html[data-page-navigating] .route-loader__ring {
  animation: route-loader-spin 900ms linear infinite;
}

html[data-page-navigating] .route-loader__ring--inner {
  animation: route-loader-spin 1400ms linear infinite reverse;
}

html[data-page-navigating] .route-loader__mark {
  animation: route-loader-breathe 1400ms ease-in-out infinite;
}

html[data-page-navigating] .route-loader__dots i {
  animation: route-loader-dot 1050ms ease-in-out infinite;
}

html[data-page-navigating] .route-loader__dots i:nth-child(2) { animation-delay: 150ms; }
html[data-page-navigating] .route-loader__dots i:nth-child(3) { animation-delay: 300ms; }

html[data-theme="light"] .route-loader {
  background: radial-gradient(circle at 50% 46%, rgb(255 255 255 / 30%), transparent 58%);
}

html[data-theme="light"] .route-loader__card {
  box-shadow:
    0 0 0 1px rgb(255 255 255 / 60%) inset;
}

@keyframes route-loader-spin {
  to { transform: rotate(360deg); }
}

@keyframes route-loader-breathe {
  0%, 100% { transform: scale(.94); }
  50% { transform: scale(1.04); }
}

@keyframes route-loader-dot {
  0%, 100% { opacity: .3; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-3px); }
}

@media (prefers-reduced-motion: reduce) {
  html[data-page-navigating] .route-loader__ring { animation-duration: 2.4s; }
  html[data-page-navigating] .route-loader__ring--inner,
  html[data-page-navigating] .route-loader__mark,
  html[data-page-navigating] .route-loader__dots i { animation: none; opacity: 1; }
  .route-loader__card { transform: none; }
}
</style>
