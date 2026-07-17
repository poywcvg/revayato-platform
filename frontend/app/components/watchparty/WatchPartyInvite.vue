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
    notifications.success('لینک کپی شد', 'حالا لینک را برای کسانی که می‌خواهی به اتاق بیایند بفرست.')
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copied.value = false }, 2200)
  } catch {
    copied.value = false
    notifications.error('کپی لینک انجام نشد', 'مرورگر اجازه کپی نداد؛ لینک را انتخاب و دستی کپی کن.')
  }
}

onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer)
})
</script>

<template>
  <section class="rounded-2xl border border-line bg-surface p-3.5" aria-labelledby="party-invite-title">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p id="party-invite-title" class="text-xs font-black text-ink">دعوت به اتاق خصوصی</p>
        <p class="mt-0.5 text-[11px] text-muted">این لینک را فقط برای کسانی بفرست که می‌خواهی وارد اتاق شوند.</p>
      </div>
      <span class="font-latin rounded-lg bg-wine px-2 py-1 text-[10px] font-bold text-secondary ring-1 ring-crimson/25">{{ inviteCode.slice(0, 6) }}…</span>
    </div>
    <div class="mt-3 flex gap-2">
      <input :value="inviteUrl" readonly dir="ltr" aria-label="لینک دعوت" class="min-w-0 flex-1 rounded-xl border border-line bg-canvas-soft px-3 text-left font-latin text-[11px] text-secondary outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20">
      <button type="button" class="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl bg-primary-500 px-3 text-xs font-black text-night-950 transition hover:bg-primary-400 active:bg-primary-600" @click="copyInvite">
        <CinematicIcon :name="copied ? 'check' : 'user-plus'" class="size-4" />
        {{ copied ? 'کپی شد' : 'کپی لینک' }}
      </button>
    </div>
  </section>
</template>
