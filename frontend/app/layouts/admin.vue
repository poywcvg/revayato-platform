<script setup lang="ts">
import Database from '~icons/lucide/database'
import ExternalLink from '~icons/lucide/external-link'
import Film from '~icons/lucide/film'
import HardDrive from '~icons/lucide/hard-drive'
import Inbox from '~icons/lucide/inbox'
import LayoutDashboard from '~icons/lucide/layout-dashboard'
import LogOut from '~icons/lucide/log-out'
import Menu from '~icons/lucide/menu'
import MessageSquare from '~icons/lucide/message-square-text'
import Plus from '~icons/lucide/plus'
import Sparkles from '~icons/lucide/sparkles'
import Tv from '~icons/lucide/tv'
import Users from '~icons/lucide/users-round'
import X from '~icons/lucide/x'
import type { Component } from 'vue'

type NavItem = { label: string; href: string; icon: Component; hint?: string }
type NavGroup = { id: string; label: string; icon: Component; items: NavItem[] }

const route = useRoute()
const authStore = useAuthStore()
const mobileNavOpen = ref(false)
const adminDrawer = useTemplateRef<HTMLElement>('adminDrawer')
let drawerPreviousFocus: HTMLElement | null = null
const drawerFocusable = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'

const catalogNav: NavItem[] = [
  { label: 'مدیریت فیلم‌ها', href: '/admin/movies', icon: Film, hint: 'جستجو، فیلتر و ویرایش' },
  { label: 'مدیریت سریال‌ها', href: '/admin/series', icon: Tv, hint: 'دانلود، دوبله و زیرنویس' },
  { label: 'افزودن دستی', href: '/admin/movies/new', icon: Plus, hint: 'ثبت عنوان بدون TMDB' },
  { label: 'افزودن از TMDB', href: '/admin/movies?tmdb=1', icon: Sparkles, hint: 'ورود با شناسه رسمی' },
]

const overviewNav: NavItem[] = [
  { label: 'داشبورد و آنالیتیکس', href: '/dashboard', icon: LayoutDashboard, hint: 'KPI، نمودار، سلامت کاتالوگ و خروجی CSV' },
  { label: 'صندوق هم‌صدا', href: '/admin/inbox', icon: Inbox, hint: 'درخواست و پشتیبانی کاربران' },
  { label: 'دیدگاه‌ها', href: '/admin/reviews', icon: MessageSquare, hint: 'مدیریت نظرات فیلم و سریال' },
]

const automationNav: NavItem[] = [
  { label: 'ورود خودکار', href: '/admin/catalog-sync', icon: Database, hint: 'همگام‌سازی زمان‌بندی‌شده' },
  { label: 'ارائه‌دهنده مجاز', href: '/admin/provider-import', icon: HardDrive, hint: 'Film2Media، Dornatv و Avasarami' },
]

const peopleNav: NavItem[] = [
  { label: 'مدیریت کاربران', href: '/admin/users', icon: Users, hint: 'دسترسی، فعال‌سازی و ساخت' },
]

const adminNavGroups: NavGroup[] = [
  { id: 'overview', label: 'نمای کلی', icon: LayoutDashboard, items: overviewNav },
  { id: 'catalog', label: 'کاتالوگ', icon: Film, items: catalogNav },
  { id: 'automation', label: 'اتوماسیون', icon: Database, items: automationNav },
  { id: 'people', label: 'کاربران', icon: Users, items: peopleNav },
]

const lineSidebarItems = computed(() => adminNavGroups.flatMap(group => group.items.map(item => item.label)))
const lineSidebarHrefs = computed(() => adminNavGroups.flatMap(group => group.items.map(item => item.href)))

function lineSidebarItemActive(href: string) {
  const [path, queryString = ''] = href.split('?')
  if (path === '/dashboard') return route.path.startsWith('/dashboard') || route.path === '/admin'
  if (path === '/admin/movies/new') return route.path === '/admin/movies/new'
  if (path === '/admin/movies' && queryString.includes('tmdb=1')) {
    return route.path === '/admin/movies' && String(route.query.tmdb) === '1'
  }
  if (path === '/admin/movies') {
    return (route.path === '/admin/movies' && String(route.query.tmdb) !== '1') || /^\/admin\/movies\/\d+/.test(route.path)
  }
  if (path === '/admin/users') return route.path.startsWith('/admin/users')
  if (path === '/admin/inbox') return route.path.startsWith('/admin/inbox')
  if (path === '/admin/reviews') return route.path.startsWith('/admin/reviews')
  if (path === '/admin/catalog-sync') return route.path.startsWith('/admin/catalog-sync')
  return route.path === path || route.path.startsWith(`${path}/`)
}

const activeLineIndex = computed(() => {
  const hrefs = lineSidebarHrefs.value
  for (let i = 0; i < hrefs.length; i++) {
    const href = hrefs[i]
    if (href && lineSidebarItemActive(href)) return i
  }
  return null
})

function handleLineSidebarClick(index: number) {
  const href = lineSidebarHrefs.value[index]
  if (href) void navigateTo(href)
}

function groupForCurrentRoute() {
  if (route.path.startsWith('/dashboard') || route.path === '/admin') return 'overview'
  if (route.path.startsWith('/admin/users')) return 'people'
  if (route.path.startsWith('/admin/provider-import') || route.path.startsWith('/admin/catalog-sync')) return 'automation'
  if (route.path.startsWith('/admin/movies') || route.path.startsWith('/admin/series')) return 'catalog'
  return 'overview'
}

const openAdminGroup = ref<string | null>(groupForCurrentRoute())

watch(() => route.fullPath, () => {
  mobileNavOpen.value = false
  openAdminGroup.value = groupForCurrentRoute()
})

function trapDrawerFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !adminDrawer.value) return
  const controls = [...adminDrawer.value.querySelectorAll<HTMLElement>(drawerFocusable)]
    .filter(control => control.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(mobileNavOpen, async (open) => {
  if (!import.meta.client) return
  document.documentElement.style.overflow = open ? 'hidden' : ''
  if (open) {
    drawerPreviousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    adminDrawer.value?.querySelector<HTMLElement>(drawerFocusable)?.focus()
  } else {
    drawerPreviousFocus?.focus()
    drawerPreviousFocus = null
  }
})

onKeyStroke('Escape', () => {
  if (mobileNavOpen.value) mobileNavOpen.value = false
})

onBeforeUnmount(() => {
  if (import.meta.client) document.documentElement.style.overflow = ''
})

async function logout() {
  await authStore.logout()
  await navigateTo('/auth/login')
}

const pageTitle = computed(() => {
  if (route.path.startsWith('/dashboard')) return 'داشبورد و آنالیتیکس'
  if (route.path === '/admin') return 'داشبورد'
  if (route.path.startsWith('/admin/inbox')) return 'صندوق هم‌صدا'
  if (route.path.startsWith('/admin/reviews')) return 'مدیریت دیدگاه‌ها'
  if (route.path.startsWith('/admin/users')) return 'مدیریت کاربران'
  if (route.path.startsWith('/admin/provider-import')) return 'ارائه‌دهنده مجاز'
  if (route.path.startsWith('/admin/catalog-sync')) return 'ورود خودکار'
  if (route.path === '/admin/series/new') return 'افزودن سریال'
  if (/\/admin\/series\/\d+/.test(route.path)) return 'ویرایش سریال'
  if (route.path.startsWith('/admin/series')) return 'مدیریت سریال‌ها'
  if (route.path === '/admin/movies/new') return 'افزودن فیلم'
  if (/\/admin\/movies\/\d+/.test(route.path)) return 'ویرایش فیلم'
  if (String(route.query.tmdb) === '1') return 'افزودن از TMDB'
  return 'مدیریت فیلم‌ها'
})
</script>

<template>
  <div class="admin-shell min-h-dvh text-[var(--admin-text)]" dir="rtl">
    <a
      href="#main-content"
      class="admin-focus fixed start-4 top-3 z-[90] -translate-y-20 rounded-xl bg-[var(--admin-primary)] px-4 py-2.5 text-sm font-black text-white shadow-lg focus:translate-y-0"
    >
      پرش به محتوای مدیریت
    </a>
    <header class="sticky top-0 z-40 flex h-14 items-center justify-between gap-3 border-b border-[var(--admin-border)] bg-[var(--admin-bg)]/92 px-4 backdrop-blur-xl lg:hidden">
      <NuxtLink to="/admin" class="admin-focus flex min-w-0 items-center gap-2.5">
        <span class="grid size-9 shrink-0 place-items-center overflow-hidden">
          <img src="/assets/brand/logo.svg" alt="" width="36" height="36" class="size-full object-contain" decoding="async">
        </span>
        <span class="min-w-0">
          <span class="block truncate text-sm font-black">استودیو روایتو</span>
          <span class="block truncate text-[10px] font-bold text-[var(--admin-muted)]">{{ pageTitle }}</span>
        </span>
      </NuxtLink>
      <button
        class="admin-focus grid size-11 place-items-center rounded-xl border border-[var(--admin-border)] bg-white"
        type="button"
        aria-label="باز کردن منوی مدیریت"
        :aria-expanded="mobileNavOpen"
        aria-controls="admin-mobile-nav"
        @click="mobileNavOpen = true"
      >
        <Menu class="size-5" />
      </button>
    </header>

    <Teleport to="body">
      <Transition name="admin-drawer">
        <div
          v-if="mobileNavOpen"
          class="admin-portal fixed inset-0 z-[70] bg-[rgb(9_20_19/55%)] backdrop-blur-sm lg:hidden"
          @click.self="mobileNavOpen = false"
        >
          <aside
            id="admin-mobile-nav"
            ref="adminDrawer"
            class="flex h-full w-[min(88vw,320px)] flex-col bg-[var(--admin-sidebar)] text-white shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-label="منوی مدیریت"
            @keydown="trapDrawerFocus"
          >
            <div class="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-4">
              <div class="flex items-center gap-2.5">
                <span class="grid size-10 place-items-center overflow-hidden">
                  <img src="/assets/brand/logo.svg" alt="" width="40" height="40" class="size-full object-contain" decoding="async">
                </span>
                <div>
                  <p class="text-sm font-black">استودیو روایتو</p>
                  <p class="text-[11px] text-white/55">مدیریت کاتالوگ</p>
                </div>
              </div>
              <button class="admin-focus grid size-11 place-items-center rounded-xl hover:bg-white/8" type="button" aria-label="بستن منو" @click="mobileNavOpen = false">
                <X class="size-5" />
              </button>
            </div>
            <div class="flex-1 overflow-y-auto px-3 py-4">
              <AdminNavigation
                v-for="group in adminNavGroups"
                :key="`mobile-${group.id}`"
                v-model:open-group="openAdminGroup"
                class="mb-1"
                :label="group.label"
                :group-id="group.id"
                :section-id="`admin-mobile-group-${group.id}`"
                :icon="group.icon"
                :items="group.items"
              />
            </div>
            <div class="border-t border-white/10 p-3">
              <div class="mb-2 rounded-2xl bg-white/6 px-3.5 py-3">
                <p class="truncate text-sm font-bold">{{ authStore.user?.username }}</p>
                <p class="truncate text-[11px] text-white/50">{{ authStore.user?.email }}</p>
              </div>
              <NuxtLink to="/" class="admin-focus flex min-h-11 items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm text-white/70 hover:bg-white/8 hover:text-white">
                <ExternalLink class="size-4" /> مشاهده سایت
              </NuxtLink>
              <button class="admin-focus flex min-h-11 w-full items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm text-white/70 hover:bg-white/8 hover:text-white" type="button" @click="logout">
                <LogOut class="size-4" /> خروج از حساب
              </button>
            </div>
          </aside>
        </div>
      </Transition>
    </Teleport>

    <aside class="admin-desktop-sidebar fixed inset-y-0 z-30 hidden flex-col bg-[var(--admin-sidebar)] text-white lg:flex">
      <div class="flex h-[4.75rem] items-center gap-3 border-b border-white/10 px-5">
        <span class="grid size-11 place-items-center overflow-hidden">
          <img src="/assets/brand/logo.svg" alt="" width="44" height="44" class="size-full object-contain" decoding="async">
        </span>
        <div class="min-w-0">
          <p class="truncate font-black tracking-tight">استودیو روایتو</p>
          <p class="truncate text-[11px] text-white/55">مدیریت کاتالوگ</p>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto px-3 py-4">
        <LineSidebar
          :items="lineSidebarItems"
          aria-label="ناوبری مدیریت"
          accent-color="#b0e4cc"
          text-color="rgba(255,255,255,0.65)"
          marker-color="rgba(255,255,255,0.35)"
          :default-active="activeLineIndex"
          :show-index="false"
          :show-marker="true"
          :proximity-radius="90"
          :max-shift="20"
          falloff="smooth"
          :marker-length="50"
          :marker-gap="12"
          :tick-scale="0.4"
          :scale-tick="true"
          :item-gap="16"
          :font-size="1"
          :smoothing="120"
          class="py-2"
          @item-click="handleLineSidebarClick"
        />
      </div>

      <div class="border-t border-white/10 p-3">
        <div class="mb-2 rounded-2xl bg-white/6 px-3.5 py-3">
          <p class="truncate text-sm font-bold">{{ authStore.user?.username }}</p>
          <p class="truncate text-[11px] text-white/50">{{ authStore.user?.email }}</p>
        </div>
        <NuxtLink to="/" class="admin-focus mb-0.5 flex min-h-11 w-full items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm text-white/65 hover:bg-white/8 hover:text-white">
          <ExternalLink class="size-4" /> مشاهده سایت
        </NuxtLink>
        <button class="admin-focus flex min-h-11 w-full items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm text-white/65 hover:bg-white/8 hover:text-white" type="button" @click="logout">
          <LogOut class="size-4" /> خروج از حساب
        </button>
      </div>
    </aside>

    <main id="main-content" tabindex="-1" class="admin-shell__main min-h-dvh">
      <div class="mx-auto w-full max-w-[var(--layout-max)] px-3 py-4 sm:px-5 sm:py-5 lg:px-6 lg:py-6">
        <slot />
      </div>
    </main>
  </div>
</template>

<style>
.admin-shell,
.admin-portal {
  --admin-sidebar-width: clamp(15.5rem, 18vw, 17.5rem);
  --admin-bg: #f4faf7;
  --admin-surface: #ffffff;
  --admin-surface-muted: #e8f4ee;
  --admin-sidebar: #091413;
  --admin-primary: #285a48;
  --admin-primary-hover: #1f4638;
  --admin-primary-rgb: 40 90 72;
  --admin-accent: #408a71;
  --admin-warm: #b0e4cc;
  --admin-text: #091413;
  --admin-muted: #5a7268;
  --admin-border: rgb(40 90 72 / 14%);
  --admin-danger: #a43d45;
  --admin-shadow: 0 14px 40px rgb(40 90 72 / 7%);
  color-scheme: light;
  font-family: var(--font-ui);
}

.admin-shell {
  background:
    radial-gradient(circle at 12% 0%, rgb(176 228 204 / 28%), transparent 28rem),
    radial-gradient(circle at 100% 8%, rgb(64 138 113 / 10%), transparent 22rem),
    var(--admin-bg);
}

.admin-shell__main {
  min-width: 0;
}

.admin-desktop-sidebar {
  inset-inline-start: 0;
  inline-size: var(--admin-sidebar-width);
  border-inline-end: 1px solid rgb(255 255 255 / 10%);
}

@media (min-width: 1024px) {
  .admin-shell__main {
    padding-inline-start: var(--admin-sidebar-width);
  }
}

.admin-focus {
  transition: color .16s ease, background-color .16s ease, border-color .16s ease, box-shadow .16s ease, transform .16s ease;
}

.admin-focus:focus-visible {
  outline: 3px solid rgb(var(--admin-primary-rgb) / 28%);
  outline-offset: 2px;
}

.admin-input {
  min-height: 2.75rem;
  max-width: 100%;
  border: 1px solid var(--admin-border);
  border-radius: .85rem;
  background: #fff;
  padding: .55rem .85rem;
  color: var(--admin-text);
  outline: none;
}

.admin-input:focus {
  border-color: var(--admin-accent);
  box-shadow: 0 0 0 3px rgb(var(--admin-primary-rgb) / 12%);
}

.admin-shell label:has(input[type="checkbox"], input[type="radio"]),
.admin-portal label:has(input[type="checkbox"], input[type="radio"]) {
  min-block-size: 2.75rem;
}

.admin-drawer-enter-active,
.admin-drawer-leave-active {
  transition: opacity .18s ease;
}

.admin-drawer-enter-active aside,
.admin-drawer-leave-active aside {
  transition: transform .2s ease;
}

.admin-drawer-enter-from,
.admin-drawer-leave-to {
  opacity: 0;
}

.admin-drawer-enter-from aside,
.admin-drawer-leave-to aside {
  transform: translateX(1.25rem);
}

@media (prefers-reduced-motion: reduce) {
  .admin-shell *,
  .admin-shell *::before,
  .admin-shell *::after {
    scroll-behavior: auto !important;
    transition-duration: .01ms !important;
    animation-duration: .01ms !important;
  }
}
</style>
