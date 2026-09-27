<script setup lang="ts">
import type { CinematicIconName } from '~/types'

interface DrawerItem { label: string, hint: string, to: string, icon: CinematicIconName, exact?: boolean, badge?: string }
const open = defineModel<boolean>('open', { default: false })
const route = useRoute()
const auth = useAuthStore()
const { watchlistIds } = useLibrary()
const { open: openSupport } = useSupportModal()
const panel = useTemplateRef<HTMLElement>('panel')
let previousFocus: HTMLElement | null = null

const profilePath = computed(() => auth.isAuthenticated ? '/profile' : `/auth/login?redirect=${encodeURIComponent(route.fullPath)}`)
const avatarInitial = computed(() => auth.user?.username?.trim().charAt(0).toUpperCase() || 'ر')
const groups = computed(() => [
  { label: 'تماشا و کشف', items: [
    { label: 'خانه', hint: 'پیشنهادهای امروز', to: '/', icon: 'home', exact: true },
    { label: 'فیلم‌ها', hint: 'آرشیو کامل فیلم', to: '/movies', icon: 'movie' },
    { label: 'سریال‌ها', hint: 'فصل‌ها و قسمت‌ها', to: '/series', icon: 'series' },
    { label: 'تازه‌ها', hint: 'جدیدترین عنوان‌ها', to: '/new', icon: 'sparkles' },
    { label: '۲۵۰ برتر IMDb', hint: 'بهترین فیلم‌ها و سریال‌های تاریخ', to: '/top250', icon: 'trophy' },
    { label: 'جدول پخش', hint: 'قسمت‌های این هفته', to: '/schedule', icon: 'calendar' },
    { label: 'انیمیشن', hint: 'برای همه سنین', to: '/movies?format=animation', icon: 'animation' },
  ] as DrawerItem[] },
  { label: 'فضای من', items: [
    { label: 'لیست من', hint: 'ذخیره‌شده‌ها', to: '/watchlist', icon: 'bookmark', badge: watchlistIds.value.length ? watchlistIds.value.length.toLocaleString('fa-IR') : undefined },
    ...(auth.isAuthenticated ? [{ label: 'درخواست‌های من', hint: 'گفت‌وگو با پشتیبانی', to: '/requests', icon: 'comments' } as DrawerItem] : []),
    { label: 'تماشای گروهی', hint: 'هم‌زمان با دوستان', to: '/watch-party', icon: 'users' },
    { label: 'بازیگران', hint: 'آثار چهره‌های محبوب', to: '/actors', icon: 'user' },
    { label: 'کشورها', hint: 'سینمای جهان', to: '/countries', icon: 'globe' },
  ] as DrawerItem[] },
  ...(auth.user?.is_staff
    ? [{ label: 'مدیریت', items: [
        { label: 'پنل مدیریت', hint: 'داشبورد و آمار', to: '/admin', icon: 'gauge' },
      ] as DrawerItem[] }]
    : []),
])

function isActive(item: DrawerItem) {
  const [path, query] = item.to.split('?')
  if (item.exact) return route.path === path
  if (query) return route.path === path && [...new URLSearchParams(query)].every(([key, value]) => route.query[key] === value)
  return route.path === path || route.path.startsWith(`${path}/`)
}
function close() { open.value = false }
function support(kind: 'content_request' | 'support') { close(); openSupport(kind) }
function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !panel.value) return
  const all = [...panel.value.querySelectorAll<HTMLElement>('a[href],button:not([disabled])')].filter(el => el.getClientRects().length)
  const first = all[0]; const last = all.at(-1)
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
let touchX = 0; let touchY = 0
function startSwipe(event: TouchEvent) { const t = event.touches[0]; if (t) { touchX = t.clientX; touchY = t.clientY } }
function moveSwipe(event: TouchEvent) { const t = event.touches[0]; if (t && t.clientX - touchX > 58 && Math.abs(t.clientX - touchX) > Math.abs(t.clientY - touchY) * 1.2) close() }

watch(() => route.fullPath, close)
watch(open, async (value) => {
  if (!import.meta.client) return
  document.documentElement.style.overflow = value ? 'hidden' : ''
  if (value) { previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null; await nextTick(); panel.value?.querySelector<HTMLElement>('button,a')?.focus({ preventScroll: true }) }
  else { previousFocus?.focus({ preventScroll: true }); previousFocus = null }
})
onKeyStroke('Escape', () => open.value && close())
onBeforeUnmount(() => { if (import.meta.client) document.documentElement.style.overflow = '' })
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer-backdrop"><button v-if="open" class="drawer-backdrop" type="button" aria-label="بستن منو" @click="close" /></Transition>
    <Transition name="drawer-panel">
      <aside v-if="open" id="mobile-sidebar" ref="panel" class="drawer" role="dialog" aria-modal="true" aria-label="منوی اصلی" dir="rtl" @keydown="trapFocus" @touchstart.passive="startSwipe" @touchmove.passive="moveSwipe">
        <span class="drawer__glow" aria-hidden="true" />
        <header class="drawer__header">
          <div class="drawer__brand"><AppLogo :compact-on-mobile="false" @click="close" /><small>سینمای تو، همیشه همراهت</small></div>
          <button type="button" class="drawer__close" aria-label="بستن منو" @click="close"><CinematicIcon name="x" class="size-5" /></button>
        </header>
        <div class="drawer__gesture" aria-hidden="true"><span /> برای بستن به راست بکش</div>

        <nav class="drawer__scroll soft-scrollbar" aria-label="ناوبری موبایل">
          <section v-for="group in groups" :key="group.label" class="drawer__group">
            <p>{{ group.label }}</p>
            <NuxtLink v-for="item in group.items" :key="item.to" :to="item.to" class="drawer__item" :class="isActive(item) && 'is-active'" :aria-current="isActive(item) ? 'page' : undefined" @click="close">
              <span class="drawer__icon"><CinematicIcon :name="item.icon" class="size-5" :stroke-width="isActive(item) ? 2.25 : 1.8" /></span>
              <span class="drawer__copy"><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
              <span v-if="item.badge" class="drawer__badge">{{ item.badge }}</span><CinematicIcon v-else name="chevron-left" class="drawer__chevron size-4" />
            </NuxtLink>
          </section>
          <section class="drawer__support">
            <button type="button" class="drawer__request" @click="support('content_request')"><span class="drawer__request-icon"><CinematicIcon name="film" class="size-5" /></span><span><strong>فیلم یا سریالت را پیدا نکردی؟</strong><small>سریع برامون درخواست بفرست</small></span><CinematicIcon name="arrow-left" class="size-4" /></button>
            <button type="button" class="drawer__support-link" @click="support('support')"><CinematicIcon name="comments" class="size-4.5" /> ارتباط با پشتیبانی</button>
          </section>
        </nav>

        <footer class="drawer__footer"><NuxtLink :to="profilePath" class="drawer__profile" @click="close">
          <span class="drawer__avatar"><img v-if="auth.user?.profile.avatar" :src="auth.user.profile.avatar" alt=""><span v-else-if="auth.isAuthenticated">{{ avatarInitial }}</span><CinematicIcon v-else name="login" class="size-5" /></span>
          <span class="drawer__profile-copy"><strong>{{ auth.isAuthenticated ? auth.user?.username : 'ورود به حساب' }}</strong><small>{{ auth.isAuthenticated ? 'پروفایل و تنظیمات حساب' : 'برای ساخت لیست شخصی وارد شو' }}</small></span><CinematicIcon name="arrow-left" class="size-4" />
        </NuxtLink></footer>
      </aside>
    </Transition>
  </Teleport>
</template>

<style scoped>
.drawer-backdrop{position:fixed;inset:0;z-index:80;border:0;background:#02050ab8;backdrop-filter:blur(2px)}.drawer{position:fixed;inset-block:0;inset-inline-start:0;z-index:85;display:flex;width:min(22rem,calc(100dvw - 1rem));flex-direction:column;overflow:hidden;border-inline-start:1px solid #ffffff14;background:#0d1118;color:#f8fafc;box-shadow:-2rem 0 5rem #00000073;padding-block:env(safe-area-inset-top,0) env(safe-area-inset-bottom,0);isolation:isolate;will-change:transform}.drawer__glow{position:absolute;inset:-7rem -8rem auto auto;z-index:-1;width:20rem;height:20rem;border-radius:50%;background:radial-gradient(circle,#e4ad4926,transparent 68%)}
.drawer__header{display:flex;align-items:center;justify-content:space-between;padding:1rem 1rem .55rem}.drawer__brand{display:flex;flex-direction:column;gap:.15rem}.drawer__brand small{padding-inline-start:2.8rem;color:#7f8794;font-size:0.75rem}.drawer__close{display:grid;width:2.65rem;height:2.65rem;place-items:center;border:1px solid #ffffff14;border-radius:.85rem;background:#ffffff0a;color:#cbd5e1;transition:transform .16s ease}.drawer__close:active{transform:scale(.92)}.drawer__gesture{display:flex;align-items:center;justify-content:center;gap:.4rem;padding:.15rem 0 .65rem;color:#596170;font-size:0.75rem}.drawer__gesture span{width:1.4rem;height:3px;border-radius:99px;background:#4b5360}
.drawer__scroll{min-height:0;flex:1;overflow-y:auto;overscroll-behavior:contain;padding:0 .8rem 1.1rem}.drawer__group{margin-top:.65rem}.drawer__group>p{padding:.35rem .65rem;color:#737c89;font-size:0.75rem;font-weight:800}.drawer__item{display:flex;min-height:3.7rem;align-items:center;gap:.7rem;margin:.18rem 0;border:1px solid transparent;border-radius:1rem;padding:.48rem .55rem;color:#aab1bd;transition:transform .18s cubic-bezier(.22,1,.36,1),background-color .18s,border-color .18s,color .18s;-webkit-tap-highlight-color:transparent}.drawer__item:active{transform:scale(.975)}.drawer__item.is-active{border-color:#e4ad492e;background:linear-gradient(110deg,#e4ad4924,#e4ad490d);color:#f7d98e}.drawer__icon{display:grid;width:2.55rem;height:2.55rem;flex:none;place-items:center;border:1px solid #ffffff0f;border-radius:.82rem;background:#ffffff08;color:#929baa;transition:transform .3s cubic-bezier(.22,1,.36,1),color .18s,background-color .18s}.is-active .drawer__icon{background:#e4ad49;color:#171109;box-shadow:0 .45rem 1.25rem #e4ad492e;transform:rotate(-3deg) scale(1.04)}.drawer__copy{display:flex;min-width:0;flex:1;flex-direction:column;gap:.16rem}.drawer__copy strong,.drawer__copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.drawer__copy strong{font-size:.82rem}.drawer__copy small{color:#697281;font-size:0.75rem}.drawer__chevron{color:#4e5663;transition:transform .2s}.is-active .drawer__chevron{color:#c79b4b;transform:translateX(-.15rem)}.drawer__badge{display:grid;min-width:1.5rem;height:1.5rem;place-items:center;border-radius:.55rem;background:#e4ad49;color:#171109;font-size:0.75rem;font-weight:900}
.drawer__support{display:grid;gap:.5rem;margin-top:1rem;border-top:1px solid #ffffff0f;padding:.9rem .15rem 0}.drawer__request{display:flex;align-items:center;gap:.65rem;border:1px solid #e4ad492e;border-radius:1rem;background:linear-gradient(120deg,#e4ad4921,#ffffff08);padding:.65rem;color:#e9edf3;text-align:start}.drawer__request-icon{display:grid;width:2.5rem;height:2.5rem;flex:none;place-items:center;border-radius:.8rem;background:#e4ad49;color:#171109}.drawer__request>span:nth-child(2){display:flex;min-width:0;flex:1;flex-direction:column}.drawer__request strong{font-size:.72rem}.drawer__request small{color:#828b98;font-size:0.75rem}.drawer__support-link{display:flex;min-height:2.8rem;align-items:center;justify-content:center;gap:.45rem;border:0;border-radius:.8rem;background:#ffffff08;color:#9fa7b4;font-size:0.75rem}
.drawer__footer{border-top:1px solid #ffffff12;padding:.7rem .9rem max(.7rem,env(safe-area-inset-bottom,0px));background:#0a0e14}.drawer__profile{display:flex;min-height:3.8rem;align-items:center;gap:.7rem;border-radius:1rem;padding:.4rem .45rem;color:#cbd5e1}.drawer__avatar{display:grid;width:2.7rem;height:2.7rem;flex:none;overflow:hidden;place-items:center;border:1px solid #e4ad493d;border-radius:.9rem;background:#e4ad491f;color:#f1c96d;font-weight:900}.drawer__avatar img{width:100%;height:100%;object-fit:cover}.drawer__profile-copy{display:flex;min-width:0;flex:1;flex-direction:column}.drawer__profile-copy strong{overflow:hidden;font-size:.75rem;text-overflow:ellipsis;white-space:nowrap}.drawer__profile-copy small{color:#697281;font-size:0.75rem}
.drawer-backdrop-enter-active,.drawer-backdrop-leave-active{transition:opacity .24s}.drawer-backdrop-enter-from,.drawer-backdrop-leave-to{opacity:0}.drawer-panel-enter-active{transition:transform .42s cubic-bezier(.16,1,.3,1),opacity .24s}.drawer-panel-leave-active{transition:transform .24s cubic-bezier(.4,0,1,1),opacity .18s}.drawer-panel-enter-from,.drawer-panel-leave-to{transform:translate3d(104%,0,0);opacity:.55}.drawer-panel-enter-active .drawer__header,.drawer-panel-enter-active .drawer__gesture,.drawer-panel-enter-active .drawer__group,.drawer-panel-enter-active .drawer__support,.drawer-panel-enter-active .drawer__footer{animation:drawer-in .42s cubic-bezier(.16,1,.3,1) both}.drawer-panel-enter-active .drawer__group:nth-of-type(2){animation-delay:.045s}.drawer-panel-enter-active .drawer__support{animation-delay:.08s}@keyframes drawer-in{from{opacity:0;transform:translate3d(1rem,.35rem,0)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.drawer-panel-enter-active,.drawer-panel-leave-active,.drawer-backdrop-enter-active,.drawer-backdrop-leave-active{transition-duration:1ms}.drawer-panel-enter-active *{animation:none!important}.drawer__item,.drawer__icon{transition:none}}
</style>
