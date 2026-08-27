<script setup lang="ts">
const route = useRoute()
const visible = ref(false)
// Always show on every visit — no long-term suppression after dismiss.
let showTimer: ReturnType<typeof setTimeout> | undefined

const excludedRoute = computed(() =>
  route.path.startsWith('/admin')
  || route.path.startsWith('/dashboard')
  || route.path.startsWith('/auth')
  || route.path.startsWith('/watch/')
  || route.path.startsWith('/watch-party/'),
)

function dismiss() {
  visible.value = false
}

onMounted(() => {
  showTimer = setTimeout(() => {
    showTimer = undefined
    if (!excludedRoute.value) visible.value = true
  }, 2500)
})

watch(excludedRoute, excluded => {
  if (excluded) visible.value = false
  else if (!showTimer) visible.value = true
})

onBeforeUnmount(() => {
  if (showTimer) clearTimeout(showTimer)
})
</script>

<template>
  <ClientOnly>
    <Transition name="donation-nudge">
      <aside v-if="visible" class="donation-nudge" aria-label="حمایت از روایتو">
        <button type="button" class="donation-nudge__close" aria-label="بستن پیام حمایت" @click="dismiss">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17" /></svg>
        </button>
        <span class="donation-nudge__heart" aria-hidden="true">♥</span>
        <div class="donation-nudge__copy">
          <strong>به جمع حامیان روایتو بپیوند</strong>
          <span>با نام دلخواه و هر مبلغی که راحتی، کنار دیگر حامیان از تیم حمایت کن.</span>
        </div>
        <a
          href="https://daramet.com/revayato"
          target="_blank"
          rel="noopener noreferrer"
          class="donation-nudge__action"
          @click="dismiss"
        >حمایت از روایتو</a>
      </aside>
    </Transition>
  </ClientOnly>
</template>

<style scoped>
.donation-nudge {
  position: fixed;
  inset-inline-end: max(1rem, env(safe-area-inset-right));
  bottom: max(1rem, env(safe-area-inset-bottom));
  z-index: 45;
  display: grid;
  width: min(25rem, calc(100vw - 2rem));
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: .7rem;
  padding: .75rem .8rem .75rem 2.4rem;
  border: 1px solid color-mix(in srgb, var(--theme-accent-primary) 28%, var(--theme-border));
  border-radius: 1.1rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 94%, transparent);
  box-shadow: 0 16px 48px rgb(0 0 0 / 18%);
  color: var(--theme-text-primary);
  direction: rtl;
  backdrop-filter: blur(16px);
}
.donation-nudge__close { position:absolute; inset-inline-start:.55rem; top:.55rem; display:grid; width:1.75rem; height:1.75rem; place-items:center; border-radius:999px; color:var(--theme-text-muted); }
.donation-nudge__close:hover { background:var(--theme-bg-elevated); color:var(--theme-text-primary); }
.donation-nudge__close svg { width:1rem; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; }
.donation-nudge__heart { display:grid; width:2.2rem; height:2.2rem; place-items:center; border-radius:.8rem; background:color-mix(in srgb, #e94b6b 13%, transparent); color:#e94b6b; font-size:1.05rem; }
.donation-nudge__copy { min-width:0; }
.donation-nudge__copy strong, .donation-nudge__copy span { display:block; }
.donation-nudge__copy strong { font-size:.78rem; font-weight:900; }
.donation-nudge__copy span { margin-top:.15rem; color:var(--theme-text-muted); font-size:.67rem; line-height:1.55; }
.donation-nudge__action { display:inline-flex; min-height:2.25rem; align-items:center; justify-content:center; white-space:nowrap; border-radius:.75rem; background:var(--theme-accent-primary); padding:0 .8rem; color:white; font-size:.7rem; font-weight:900; }
.donation-nudge__action:hover { filter:brightness(1.08); }
.donation-nudge-enter-active, .donation-nudge-leave-active { transition:opacity .22s ease, transform .22s ease; }
.donation-nudge-enter-from, .donation-nudge-leave-to { opacity:0; transform:translateY(.75rem); }
@media (max-width: 520px) {
  .donation-nudge { grid-template-columns:auto minmax(0, 1fr); }
  .donation-nudge__action { grid-column:1 / -1; width:100%; }
}
@media (prefers-reduced-motion: reduce) {
  .donation-nudge-enter-active, .donation-nudge-leave-active { transition:none; }
}
</style>
