<script setup lang="ts">
const route = useRoute()
const year = new Date().getFullYear()

const quickLinks = [
  { label: 'فیلم‌ها', to: '/movies' },
  { label: 'سریال‌ها', to: '/series' },
  { label: 'تازه‌ها', to: '/new' },
  { label: 'اپلیکیشن', to: '/app' },
]

const supportLinks = [
  { label: 'درخواست فیلم یا سریال', to: '/contact?subject=content_request' },
  { label: 'حمایت از روایتو', to: 'https://daramet.com/revayato', external: true },
  { label: 'درباره ما', to: '/about' },
  { label: 'تماس با ما', to: '/contact' },
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
      <div class="site-footer__grid">
        <div class="site-footer__brand">
          <NuxtLink to="/" class="site-footer__logo" aria-label="روایتو، صفحه اصلی">
            روایتو
          </NuxtLink>
          <p class="site-footer__tagline">
            تماشای آنلاین فیلم و سریال با زیرنویس فارسی، روی موبایل، تبلت و کامپیوتر.
          </p>
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

        <nav class="site-footer__col" aria-label="دسترسی سریع">
          <h2 class="site-footer__heading">دسترسی سریع</h2>
          <ul class="site-footer__list">
            <li v-for="item in quickLinks" :key="item.to">
              <NuxtLink
                :to="item.to"
                class="site-footer__link"
                :class="{ 'is-active': isActive(item.to) }"
                :aria-current="isActive(item.to) ? 'page' : undefined"
              >
                {{ item.label }}
              </NuxtLink>
            </li>
          </ul>
        </nav>

        <nav class="site-footer__col" aria-label="پشتیبانی و راهنما">
          <h2 class="site-footer__heading">پشتیبانی</h2>
          <ul class="site-footer__list">
            <li v-for="item in supportLinks" :key="item.to">
              <a
                v-if="item.external"
                :href="item.to"
                target="_blank"
                rel="noopener noreferrer"
                class="site-footer__link site-footer__link--donation"
              >♥ {{ item.label }}</a>
              <NuxtLink
                v-else
                :to="item.to"
                class="site-footer__link"
                :class="{ 'is-active': isActive(item.to) }"
                :aria-current="isActive(item.to) ? 'page' : undefined"
              >
                {{ item.label }}
              </NuxtLink>
            </li>
          </ul>
        </nav>
      </div>

      <div class="site-footer__bar">
        <p class="site-footer__copy">© {{ year }} روایتو — همه حقوق محفوظ است.</p>
        <a
          href="https://t.me/revayato"
          target="_blank"
          rel="noopener noreferrer"
          class="site-footer__handle"
          dir="ltr"
        >@revayato</a>
      </div>
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
  padding-block: 2rem max(1.25rem, env(safe-area-inset-bottom));
}

.site-footer__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
}

@media (min-width: 640px) {
  .site-footer__grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (min-width: 1024px) {
  .site-footer__grid {
    grid-template-columns: minmax(0, 1.5fr) 1fr 1fr;
    gap: 3rem;
  }
}

.site-footer__logo {
  display: inline-block;
  background: linear-gradient(120deg, var(--theme-accent-primary), var(--theme-accent-crimson, var(--theme-accent-primary)));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-size: 1.35rem;
  font-weight: 900;
}

.site-footer__tagline {
  margin-top: .55rem;
  max-width: 22rem;
  color: var(--theme-text-secondary);
  font-size: .78rem;
  line-height: 1.9;
}

.site-footer__telegram {
  display: inline-flex;
  min-height: 2.25rem;
  margin-top: 1rem;
  padding-inline: 10px 12px;
  align-items: center;
  gap: 6px;
  border: 1px solid color-mix(in srgb, #2aabee 24%, var(--theme-border));
  border-radius: 9999px;
  background: color-mix(in srgb, #2aabee 7%, var(--theme-bg-elevated));
  color: var(--theme-text-secondary);
  font-size: .72rem;
  font-weight: 700;
  transition: border-color 160ms ease, background-color 160ms ease, color 160ms ease, transform 160ms ease;
}

.site-footer__telegram-icon {
  width: 17px;
  height: 17px;
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

.site-footer__heading {
  margin: 0 0 .65rem;
  color: var(--theme-text-primary);
  font-size: .82rem;
  font-weight: 800;
}

.site-footer__list {
  display: flex;
  flex-direction: column;
  gap: .15rem;
}

.site-footer__link {
  display: inline-flex;
  min-height: 2rem;
  align-items: center;
  color: var(--theme-text-muted);
  font-size: .75rem;
  transition: color 160ms ease;
}

.site-footer__link:hover,
.site-footer__link.is-active {
  color: var(--theme-accent-primary);
}

.site-footer__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: .5rem 1rem;
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid color-mix(in srgb, var(--theme-border) 60%, transparent);
}

.site-footer__copy {
  margin: 0;
  color: var(--theme-text-muted);
  font-size: .7rem;
}

.site-footer__handle {
  color: var(--theme-text-muted);
  font-family: var(--font-latin-ui);
  font-size: .7rem;
  transition: color 160ms ease;
}

.site-footer__handle:hover {
  color: #2aabee;
}

@media (max-width: 379px) {
  .site-footer__telegram-handle,
  .site-footer__handle {
    display: none;
  }
}
</style>
