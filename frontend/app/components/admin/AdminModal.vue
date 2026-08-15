<script setup lang="ts">
import X from '~icons/lucide/x'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  description?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  closeable?: boolean
}>(), {
  description: '',
  size: 'md',
  closeable: true,
})

const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
let previouslyFocused: HTMLElement | null = null

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function close() {
  if (props.closeable) emit('close')
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.open) close()
  if (event.key !== 'Tab' || !props.open || !panel.value) return
  const controls = [...panel.value.querySelectorAll<HTMLElement>(focusableSelector)]
    .filter(control => !control.hidden && control.getClientRects().length > 0)
  if (!controls.length) {
    event.preventDefault()
    panel.value.focus()
    return
  }
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}

watch(() => props.open, async (open) => {
  if (!import.meta.client) return
  document.documentElement.style.overflow = open ? 'hidden' : ''
  if (open) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    panel.value?.focus()
  } else {
    previouslyFocused?.focus()
    previouslyFocused = null
  }
})

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  if (import.meta.client) document.documentElement.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="admin-modal">
      <div
        v-if="open"
        class="admin-portal fixed inset-0 z-[80] grid items-end bg-[rgb(9_20_19/58%)] p-0 backdrop-blur-[3px] sm:place-items-center sm:p-5"
        role="presentation"
        @mousedown.self="close"
      >
        <section
          ref="panel"
          tabindex="-1"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
          class="flex max-h-[calc(100dvh_-_1rem_-_env(safe-area-inset-top)_-_env(safe-area-inset-bottom))] w-[min(100%,calc(100dvw-1rem))] flex-col overflow-hidden rounded-t-[24px] border border-[var(--admin-border)] bg-[var(--admin-bg)] text-[var(--admin-text)] shadow-2xl outline-none sm:max-h-[calc(100dvh-2.5rem)] sm:rounded-[24px]"
          :class="{
            'max-w-md': size === 'sm',
            'max-w-2xl': size === 'md',
            'max-w-4xl': size === 'lg',
            'max-w-[72rem]': size === 'xl',
          }"
        >
          <header class="flex shrink-0 items-start gap-4 border-b border-[var(--admin-border)] bg-[var(--admin-surface)] px-5 py-4 sm:px-6">
            <div class="min-w-0 flex-1">
              <h2 class="text-lg font-black sm:text-xl">{{ title }}</h2>
              <p v-if="description" class="mt-1 text-xs leading-6 text-[var(--admin-muted)] sm:text-sm">{{ description }}</p>
            </div>
            <button
              v-if="closeable"
              type="button"
              class="admin-focus grid size-11 shrink-0 place-items-center rounded-xl text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)] hover:text-[var(--admin-text)]"
              aria-label="بستن پنجره"
              @click="close"
            >
              <X class="size-5" />
            </button>
          </header>
          <div class="min-h-0 flex-1 overflow-y-auto bg-[var(--admin-bg)]">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="shrink-0 border-t border-[var(--admin-border)] bg-[var(--admin-surface)] px-5 py-4 sm:px-6">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.admin-modal-enter-active,
.admin-modal-leave-active {
  transition: opacity .18s ease;
}

.admin-modal-enter-active section,
.admin-modal-leave-active section {
  transition: transform .2s ease, opacity .18s ease;
}

.admin-modal-enter-from,
.admin-modal-leave-to {
  opacity: 0;
}

.admin-modal-enter-from section,
.admin-modal-leave-to section {
  opacity: 0;
  transform: translateY(14px) scale(.985);
}
</style>
