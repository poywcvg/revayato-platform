<script setup lang="ts">
import LayoutDashboard from '~icons/lucide/layout-dashboard'
import Activity from '~icons/lucide/activity'
import Film from '~icons/lucide/film'
import DownloadCloud from '~icons/lucide/download-cloud'
import Tv from '~icons/lucide/tv'
import GalleryHorizontal from '~icons/lucide/gallery-horizontal'
import Users from '~icons/lucide/users-round'
import MessageSquare from '~icons/lucide/message-square'
import Headset from '~icons/lucide/headset'
import HeartPulse from '~icons/lucide/heart-pulse'
import Radar from '~icons/lucide/radar'
import ExternalLink from '~icons/lucide/external-link'
import LogOut from '~icons/lucide/log-out'
import Menu from '~icons/lucide/menu'
import X from '~icons/lucide/x'
import type { Component } from 'vue'

const route = useRoute()
const auth = useAuthStore()

// Live interaction counters power the nav badges (نقدهای بی‌پاسخ + درخواست‌های خوانده‌نشده).
const { overview, refreshOverview } = useAdminInteraction()
type BadgeKey = 'reviews' | 'support'

interface NavItem { label: string, to: string, icon: Component, exact?: boolean, badge?: BadgeKey }
interface NavGroup { label: string, items: NavItem[] }

const groups: NavGroup[] = [
  {
    label: 'کنترل',
    items: [
      { label: 'داشبورد', to: '/admin', icon: LayoutDashboard, exact: true },
      { label: 'عملیات و خزنده‌ها', to: '/admin/operations', icon: Radar },
      { label: 'تحلیل رفتار', to: '/admin/behavior', icon: Activity },
    ],
  },
  {
    label: 'محتوا',
    items: [
      { label: 'فیلم‌ها', to: '/admin/movies', icon: Film },
      { label: 'سریال‌ها', to: '/admin/series', icon: Tv },
      { label: 'اسلایدر خانه', to: '/admin/slider', icon: GalleryHorizontal },
      { label: 'ورود محتوا', to: '/admin/import', icon: DownloadCloud },
      { label: 'سلامت محتوا', to: '/admin/health', icon: HeartPulse },
    ],
  },
  {
    label: 'جامعه',
    items: [
      { label: 'کاربران', to: '/admin/users', icon: Users },
      { label: 'نقدها', to: '/admin/reviews', icon: MessageSquare, badge: 'reviews' },
      { label: 'درخواست‌ها', to: '/admin/support', icon: Headset, badge: 'support' },
    ],
  },
]

function badgeCount(item: NavItem): number {
  if (!item.badge || !overview.value) return 0
  return item.badge === 'reviews' ? overview.value.reviews.unanswered : overview.value.support.unread
}

onMounted(() => {
  void refreshOverview()
  // Keep the badges fresh while the panel stays open.
  const timer = setInterval(() => { void refreshOverview() }, 60_000)
  onBeforeUnmount(() => clearInterval(timer))
})

function isActive(item: NavItem) {
  if (item.exact) return route.path === item.to
  return route.path === item.to || route.path.startsWith(`${item.to}/`)
}

const pageTitle = computed(() => {
  for (const g of groups) {
    for (const it of g.items) {
      if (isActive(it)) return it.label
    }
  }
  return 'مدیریت'
})

const drawerOpen = ref(false)
watch(() => route.path, () => { drawerOpen.value = false })

const userInitial = computed(() => (auth.user?.username || auth.user?.email || '؟').trim().charAt(0).toUpperCase())

async function onLogout() {
  await auth.logout()
  await navigateTo('/')
}
</script>

<template>
  <div class="rv-admin">
    <div class="rv-admin__aura" />

    <!-- Mobile top bar -->
    <div class="sticky top-0 z-40 flex items-center justify-between gap-3 border-b border-[var(--rv-border)] bg-[var(--rv-bg)]/85 px-4 py-3 lg:hidden">
      <button type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-10 !px-3" @click="drawerOpen = true">
        <Menu class="size-5" />
      </button>
      <span class="text-sm font-black">{{ pageTitle }}</span>
      <NuxtLink to="/" class="rv-btn rv-btn--subtle rv-focus !min-h-10 !px-3" aria-label="بازگشت به سایت">
        <ExternalLink class="size-4" />
      </NuxtLink>
    </div>

    <div class="relative z-10 mx-auto flex w-full max-w-[1600px]">
      <!-- Sidebar (desktop) + drawer (mobile) -->
      <Transition name="rv-fade">
        <div v-if="drawerOpen" class="fixed inset-0 z-40 bg-black/60 lg:hidden" @click="drawerOpen = false" />
      </Transition>

      <aside
        class="fixed inset-y-0 right-0 z-50 flex w-[var(--rv-sidebar-w)] flex-col border-l border-[var(--rv-border)] bg-[var(--rv-bg-soft)] transition-transform duration-300 lg:sticky lg:top-0 lg:z-10 lg:h-screen lg:translate-x-0"
        :class="drawerOpen ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'"
      >
        <div class="flex items-center justify-between gap-2 px-5 pb-4 pt-5">
          <NuxtLink to="/admin" class="rv-focus flex items-center gap-2.5">
            <span class="grid size-9 place-items-center rounded-[var(--rv-radius-sm)] bg-[var(--rv-accent)] text-[var(--rv-on-accent)]">
              <span class="text-base font-black">ر</span>
            </span>
            <span class="leading-tight">
              <span class="block text-sm font-black text-[var(--rv-text)]">روایتو</span>
              <span class="block text-[11px] font-bold text-[var(--rv-faint)]">پنل مدیریت</span>
            </span>
          </NuxtLink>
          <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9 !px-2 lg:hidden" @click="drawerOpen = false">
            <X class="size-5" />
          </button>
        </div>

        <nav class="flex-1 space-y-5 overflow-y-auto px-3 py-2">
          <div v-for="group in groups" :key="group.label">
            <p class="px-3 pb-2 text-[11px] font-black uppercase tracking-wider text-[var(--rv-faint)]">{{ group.label }}</p>
            <ul class="space-y-1">
              <li v-for="item in group.items" :key="item.to">
                <NuxtLink
                  :to="item.to"
                  class="rv-focus group relative flex items-center gap-3 rounded-[var(--rv-radius-sm)] px-3 py-2.5 text-sm font-bold transition"
                  :class="isActive(item)
 ? 'bg-[var(--rv-accent-soft)] text-[var(--rv-text)]'
                    : 'text-[var(--rv-muted)] hover:bg-[var(--rv-surface-2)] hover:text-[var(--rv-text)]'"
                >
                  <span
                    v-if="isActive(item)"
                    class="absolute inset-y-2 right-0 w-[3px] rounded-full bg-[var(--rv-accent)]"
                  />
                  <component
                    :is="item.icon"
                    class="size-[18px] shrink-0 transition"
                    :style="isActive(item) ? { color: 'var(--rv-accent)' } : {}"
                  />
                  <span class="truncate">{{ item.label }}</span>
                  <span
                    v-if="badgeCount(item) > 0"
                    class="mr-auto grid min-w-5 place-items-center rounded-full bg-[var(--rv-warning-soft)] px-1.5 py-0.5 text-[11px] font-black tabular-nums text-[var(--rv-warning)]"
                  >
                    {{ badgeCount(item).toLocaleString('fa-IR') }}
                  </span>
                </NuxtLink>
              </li>
            </ul>
          </div>
        </nav>

        <div class="border-t border-[var(--rv-border)] p-3">
          <div class="flex items-center gap-3 rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface)] px-3 py-2.5">
            <span class="grid size-9 shrink-0 place-items-center rounded-full bg-[var(--rv-accent-soft)] text-sm font-black text-[var(--rv-accent)]">{{ userInitial }}</span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-xs font-black text-[var(--rv-text)]">{{ auth.user?.username || 'مدیر' }}</p>
              <p class="truncate text-[11px] font-semibold text-[var(--rv-faint)]">{{ auth.user?.email }}</p>
            </div>
            <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9 !px-2" title="خروج" @click="onLogout">
              <LogOut class="size-4" />
            </button>
          </div>
          <NuxtLink to="/" class="rv-btn rv-btn--subtle rv-focus mt-2 w-full !justify-start">
            <ExternalLink class="size-4" />
            بازگشت به سایت
          </NuxtLink>
        </div>
      </aside>

      <!-- Main -->
      <main class="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
        <div class="mx-auto w-full max-w-[1200px]">
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.rv-fade-enter-active,
.rv-fade-leave-active { transition: opacity 0.25s ease; }
.rv-fade-enter-from,
.rv-fade-leave-to { opacity: 0; }
</style>
