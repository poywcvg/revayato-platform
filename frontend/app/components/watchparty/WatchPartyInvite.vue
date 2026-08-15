<script setup lang="ts">
const props = defineProps<{
  inviteCode: string
  inviteUrl: string
}>()

const copied = ref(false)
const notifications = useNotifications()
let copiedTimer: ReturnType<typeof setTimeout> | undefined

async function copyInvite() {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(props.inviteUrl)
    copied.value = true
    notifications.success('لینک کپی شد', 'لینک را برای دوستانت بفرست تا به اتاق بیایند.')
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copied.value = false }, 2200)
  } catch {
    copied.value = false
    notifications.error('کپی لینک انجام نشد', 'مرورگر اجازه کپی خودکار نداد.', {
      reason: 'لینک را انتخاب کن و دستی کپی کن.',
      inbox: true,
    })
  }
}

async function shareInvite() {
  if (!import.meta.client) return
  try {
    if (navigator.share) {
      await navigator.share({
        title: 'دعوت به تماشای گروهی',
        text: 'با من هم‌زمان تماشا کن',
        url: props.inviteUrl,
      })
      return
    }
    await copyInvite()
  } catch {
    // User cancelled share sheet.
  }
}

onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer)
})
</script>

<template>
  <section class="rounded-2xl border border-white/8 bg-white/[.03] p-3.5" aria-labelledby="party-invite-title">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p id="party-invite-title" class="text-xs font-black text-white">دعوت به اتاق</p>
        <p class="mt-0.5 text-[11px] leading-5 text-white/40">فقط کسانی که لینک دارند وارد می‌شوند.</p>
      </div>
      <span class="font-latin rounded-lg bg-wine/80 px-2 py-1 text-[10px] font-bold text-white/70 ring-1 ring-crimson/25">
        {{ inviteCode.slice(0, 8) }}
      </span>
    </div>
    <div class="mt-3">
      <input
        :value="inviteUrl"
        readonly
        dir="ltr"
        aria-label="لینک دعوت"
        class="min-h-11 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-left font-latin text-[11px] text-white/55 outline-none focus:border-info/40 focus:ring-2 focus:ring-info/15"
        @focus="($event.target as HTMLInputElement).select()"
      >
    </div>
    <div class="mt-2 grid grid-cols-2 gap-2">
      <button
        type="button"
        class="party-invite-btn party-invite-btn--copy"
        :class="copied && 'is-done'"
        @click="copyInvite"
      >
        <CinematicIcon :name="copied ? 'check' : 'user-plus'" class="size-3.5" />
        {{ copied ? 'شد' : 'کپی' }}
      </button>
      <button
        type="button"
        class="party-invite-btn party-invite-btn--share"
        @click="shareInvite"
      >
        <CinematicIcon name="share" class="size-3.5" />
        اشتراک
      </button>
    </div>
  </section>
</template>

<style scoped>
.party-invite-btn {
  display: inline-flex;
  min-height: 2.75rem;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  border-radius: 0.85rem;
  border: 1px solid transparent;
  padding-inline: 0.75rem;
  font-size: 0.75rem;
  font-weight: 900;
  transition:
    transform 160ms ease,
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 180ms ease;
}

.party-invite-btn:hover {
  transform: translateY(-1px);
}

.party-invite-btn:active {
  transform: scale(0.98);
}

.party-invite-btn--copy {
  color: #071419;
  background: #38bdf8;
}

.party-invite-btn--copy:hover {
  background: #7dd3fc;
  box-shadow: 0 8px 20px rgb(56 189 248 / 28%);
}

.party-invite-btn--copy.is-done {
  color: #07150d;
  background: #4ade80;
}

.party-invite-btn--share {
  color: #b0e4cc;
  background: rgb(176 228 204 / 12%);
  border-color: rgb(176 228 204 / 28%);
}

.party-invite-btn--share:hover {
  color: #ecfdf5;
  background: rgb(176 228 204 / 24%);
  border-color: rgb(176 228 204 / 48%);
  box-shadow: 0 8px 20px rgb(176 228 204 / 16%);
}
</style>
