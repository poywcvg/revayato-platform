<script setup lang="ts">
const route = useRoute()
const year = new Date().getFullYear()

const links = [
  { label: 'فیلم‌ها', to: '/movies' },
  { label: 'سریال‌ها', to: '/series' },
  { label: 'تازه‌ها', to: '/new' },
  { label: 'درباره ما', to: '/about' },
  { label: 'تماس', to: '/contact' },
  { label: 'قوانین', to: '/terms' },
  { label: 'حریم خصوصی', to: '/privacy' },
]

function linkPath(to: string) {
  return to.split(/[?#]/, 1)[0] || '/'
}

function isActive(to: string) {
  const path = linkPath(to)
  return route.path === path || (path !== '/' && route.path.startsWith(`${path}/`))
}
</script>

<template>
  <footer class="site-footer">
    <div class="page-shell site-footer__inner">
      <div class="site-footer__meta">
        <p class="site-footer__copy">© {{ year }} روایتو</p>
        <a
          href="https://t.me/revayato"
          target="_blank"
          rel="noopener noreferrer"
          class="site-footer__telegram"
          aria-label="کانال تلگرام روایتو، @revayato؛ باز کردن در پنجره جدید"
        >
          <svg
            class="site-footer__telegram-icon"
            viewBox="0 0 32 32"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M16 0a16 16 0 1 0 0 32 16 16 0 0 0 0-32Zm7.84 10.72-2.4 11.32c-.18.8-.66 1-1.33.62l-3.66-2.7-1.76 1.7c-.2.2-.36.36-.74.36l.27-3.72L21 12.17c.3-.27-.06-.41-.46-.15l-8.39 5.28-3.61-1.13c-.78-.24-.8-.78.17-1.16l14.11-5.44c.66-.25 1.23.14 1.02 1.15Z" />
          </svg>
          <span>تلگرام</span>
          <span class="site-footer__telegram-handle" dir="ltr">@revayato</span>
        </a>
      </div>

      <nav class="site-footer__nav" aria-label="پیوندهای پایین صفحه">
        <NuxtLink
          v-for="item in links"
          :key="item.to"
          :to="item.to"
          :class="{ 'is-active': isActive(item.to) }"
          :aria-current="isActive(item.to) ? 'page' : undefined"
        >
          {{ item.label }}
        </NuxtLink>
      </nav>
    </div>
  </footer>
</template>

<style scoped>
.site-footer {
  border-top: 1px solid var(--theme-border);
  background: var(--theme-bg-main);
  color: var(--theme-text-muted);
}

.site-footer__inner {
  display: flex;
  min-height: 52px;
  padding-block: 14px max(14px, env(safe-area-inset-bottom));
  align-items: center;
  justify-content: space-between;
  gap: 16px 28px;
}

.site-footer__copy {
  margin: 0;
  color: var(--theme-text-muted);
  font-size: .7rem;
  white-space: nowrap;
}

.site-footer__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
}

.site-footer__telegram {
  display: inline-flex;
  min-height: 36px;
  padding-inline: 9px 11px;
  align-items: center;
  gap: 6px;
  border: 1px solid color-mix(in srgb, #2aabee 24%, var(--theme-border));
  border-radius: 9999px;
  background: color-mix(in srgb, #2aabee 7%, var(--theme-bg-elevated));
  color: var(--theme-text-secondary);
  font-size: .7rem;
  font-weight: 700;
  transition: border-color 160ms ease, background-color 160ms ease, color 160ms ease, transform 160ms ease;
}

.site-footer__telegram-icon {
  width: 18px;
  height: 18px;
  flex: none;
  color: #2aabee;
}

.site-footer__telegram-handle {
  color: var(--theme-text-muted);
  font-family: var(--font-latin-ui);
  font-size: .66rem;
  font-weight: 600;
}

.site-footer__telegram:hover,
.site-footer__telegram:focus-visible {
  border-color: color-mix(in srgb, #2aabee 58%, var(--theme-border));
  background: color-mix(in srgb, #2aabee 13%, var(--theme-bg-elevated));
  color: var(--theme-text-primary);
  transform: translateY(-1px);
}

.site-footer__nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 2px 2px;
}

.site-footer__nav a {
  display: inline-flex;
  min-height: 32px;
  padding-inline: 8px;
  align-items: center;
  color: var(--theme-text-muted);
  font-size: .7rem;
  font-weight: 600;
  transition: color 160ms ease;
}

.site-footer__nav a:hover,
.site-footer__nav a.is-active {
  color: var(--theme-accent-primary);
}

@media (max-width: 639px) {
  .site-footer__inner {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .site-footer__meta {
    width: 100%;
    justify-content: space-between;
  }

  .site-footer__nav {
    width: 100%;
    justify-content: flex-start;
    gap: 0;
  }

  .site-footer__nav a {
    min-height: 2.75rem;
    padding-inline: .55rem;
    font-size: .72rem;
  }

  .site-footer__telegram {
    min-height: 2.75rem;
  }
}

@media (max-width: 379px) {
  .site-footer__telegram-handle {
    display: none;
  }
}
</style>
