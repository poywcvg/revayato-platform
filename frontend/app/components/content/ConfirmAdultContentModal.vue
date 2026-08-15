<script setup lang="ts">
const props = defineProps<{ open: boolean; title?: string }>()
const emit = defineEmits<{ confirm: []; close: [] }>()
const confirmButton = useTemplateRef<HTMLButtonElement>('confirmButton')
const dialog = useTemplateRef<HTMLElement>('dialog')
let previouslyFocused: HTMLElement | null = null
const focusableSelector = 'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'

function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !dialog.value) return
  const controls = [...dialog.value.querySelectorAll<HTMLElement>(focusableSelector)]
    .filter(control => control.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)
  if (!first || !last) {
    event.preventDefault()
    dialog.value.focus()
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.open, async (open) => {
  if (!import.meta.client) return
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    confirmButton.value?.focus()
  } else {
    previouslyFocused?.focus()
    previouslyFocused = null
  }
}, { immediate: true })

onKeyStroke('Escape', () => { if (props.open) emit('close') })
onBeforeUnmount(() => { if (import.meta.client) document.body.style.overflow = '' })
</script>

<template>
  <Teleport to="body">
    <Transition enter-active-class="transition duration-200" enter-from-class="opacity-0" leave-active-class="transition duration-150" leave-to-class="opacity-0">
      <div v-if="open" class="fixed inset-0 z-[100] flex cursor-pointer items-end justify-center bg-[var(--theme-overlay-backdrop)] pt-4 backdrop-blur-sm sm:grid sm:place-items-center sm:p-4" role="presentation" @click.self="emit('close')">
        <section
          ref="dialog"
          tabindex="-1"
          role="dialog"
          aria-modal="true"
          aria-labelledby="adult-modal-title"
          aria-describedby="adult-modal-description"
          class="max-h-[calc(100dvh_-_1rem_-_env(safe-area-inset-top)_-_env(safe-area-inset-bottom))] w-[min(100%,calc(100dvw-1rem))] max-w-md cursor-default overflow-y-auto rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] text-ink shadow-2xl shadow-black/40 outline-none ring-1 ring-line sm:rounded-3xl sm:pb-0"
          @keydown="trapFocus"
        >
          <div class="border-b border-error/25 bg-error/[.07] p-5 sm:p-6">
            <span class="theme-media-dark grid h-12 w-12 place-items-center rounded-2xl bg-error text-white"><span class="text-lg font-black">۱۸+</span></span>
            <p class="mt-4 text-xs font-black text-error">مناسب بزرگسالان</p>
            <h2 id="adult-modal-title" class="mt-1 text-xl font-black text-ink">تأیید مشاهده محتوا</h2>
            <p v-if="title" class="mt-1 text-sm font-bold text-secondary">{{ title }}</p>
          </div>
          <div class="p-5 sm:p-6">
            <p id="adult-modal-description" class="text-sm leading-7 text-secondary">این عنوان در رده سنی بزرگسال قرار دارد و ممکن است برای همه مناسب نباشد. برای ادامه، تأیید کنید.</p>
            <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row">
              <button type="button" class="ui-secondary-button flex-1" @click="emit('close')">بازگشت</button>
              <button ref="confirmButton" type="button" class="ui-primary-button flex-1" @click="emit('confirm')">ادامه پخش</button>
            </div>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
