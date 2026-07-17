<script setup lang="ts">
const open = ref(false)
const panel = useTemplateRef<HTMLElement>('panel')
const { notifications, unreadCount, markRead, markAllRead, clear } = useNotifications()

onClickOutside(panel, () => { open.value = false })
onKeyStroke('Escape', () => { open.value = false })

function openItem(id: string) {
  markRead(id)
  open.value = false
}
</script>

<template>
  <div ref="panel" class="relative">
    <button type="button" class="relative grid size-11 place-items-center rounded-xl text-slate-400 ring-1 ring-transparent transition-colors hover:bg-white/[.055] hover:text-ink" :class="open && 'bg-primary-500/12 text-primary-300 ring-primary-500/20'" aria-label="اعلان‌ها" :aria-expanded="open" aria-controls="notification-panel" @click="open = !open">
      <CinematicIcon :name="unreadCount ? 'bell-ring' : 'bell'" class="size-5" />
      <span v-if="unreadCount" class="absolute -left-1 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full bg-crimson px-1 text-[9px] font-black text-ink ring-2 ring-night-950 tabular-nums">{{ unreadCount > 9 ? '9+' : unreadCount }}</span>
    </button>

    <Transition enter-active-class="transition duration-150" enter-from-class="translate-y-1 scale-[.98] opacity-0" leave-active-class="transition duration-100" leave-to-class="translate-y-1 scale-[.98] opacity-0">
      <section v-if="open" id="notification-panel" class="fixed inset-x-3 top-[132px] z-[70] max-h-[min(68dvh,520px)] overflow-hidden rounded-2xl border border-line bg-surface/98 shadow-2xl shadow-black/55 backdrop-blur-xl md:absolute md:inset-x-auto md:left-0 md:top-14 md:w-[380px] md:max-h-[min(72dvh,520px)]" aria-label="مرکز اعلان‌ها">
        <header class="flex items-center justify-between gap-3 border-b border-line p-4">
          <div><h2 class="text-sm font-black text-ink">اعلان‌ها</h2><p class="mt-0.5 text-[11px] text-muted">{{ unreadCount ? `${unreadCount} پیام خوانده‌نشده` : 'همه پیام‌ها را دیده‌ای' }}</p></div>
          <button v-if="unreadCount" type="button" class="min-h-9 rounded-lg px-2 text-[11px] font-black text-primary-300 hover:bg-primary-500/10" @click="markAllRead">خواندن همه</button>
        </header>
        <div v-if="notifications.length" class="cinematic-scrollbar max-h-[400px] overflow-y-auto p-2">
          <component :is="item.href ? resolveComponent('NuxtLink') : 'button'" v-for="item in notifications" :key="item.id" :to="item.href" type="button" class="relative flex w-full items-start gap-3 rounded-xl p-3 text-right transition-colors hover:bg-white/[.045]" @click="openItem(item.id)">
            <span class="grid size-9 shrink-0 place-items-center rounded-xl" :class="{ 'bg-success/10 text-success': item.type === 'success', 'bg-error/10 text-error': item.type === 'error', 'bg-warning/10 text-warning': item.type === 'warning', 'bg-info/10 text-info': item.type === 'info' }"><CinematicIcon :name="item.type === 'success' ? 'check-circle' : item.type === 'error' || item.type === 'warning' ? 'alert-triangle' : 'info'" class="size-4.5" /></span>
            <span class="min-w-0 flex-1"><span class="block text-xs font-black text-ink">{{ item.title }}</span><span class="mt-1 block text-[11px] leading-5 text-muted">{{ item.message }}</span><span class="mt-1.5 block font-latin text-[9px] text-disabled">{{ new Intl.DateTimeFormat('fa-IR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(item.createdAt)) }}</span></span>
            <span v-if="!item.read" class="mt-1.5 size-2 shrink-0 rounded-full bg-primary-500" aria-label="خوانده‌نشده" />
          </component>
        </div>
        <div v-else class="grid min-h-48 place-items-center p-6 text-center"><div><span class="mx-auto grid size-12 place-items-center rounded-2xl bg-elevated text-muted"><CinematicIcon name="bell" class="size-6" /></span><p class="mt-3 text-sm font-black text-ink">هنوز اعلانی نداری</p><p class="mt-1 text-xs leading-6 text-muted">خبرهای مهم حساب و تماشا اینجا دیده می‌شوند.</p></div></div>
        <footer v-if="notifications.length" class="border-t border-line p-2 text-center"><button type="button" class="min-h-9 rounded-lg px-3 text-[11px] font-bold text-muted hover:bg-error/8 hover:text-error" @click="clear">پاک کردن اعلان‌ها</button></footer>
      </section>
    </Transition>
  </div>
</template>
