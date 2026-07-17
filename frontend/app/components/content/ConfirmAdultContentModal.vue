<script setup lang="ts">
const props = defineProps<{ open: boolean; title?: string }>()
const emit = defineEmits<{ confirm: []; close: [] }>()
const confirmButton = useTemplateRef<HTMLButtonElement>('confirmButton')

watch(() => props.open, async (open) => {
  if (!import.meta.client) return
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) {
    await nextTick()
    confirmButton.value?.focus()
  }
}, { immediate: true })

onKeyStroke('Escape', () => { if (props.open) emit('close') })
onBeforeUnmount(() => { if (import.meta.client) document.body.style.overflow = '' })
</script>

<template>
  <Teleport to="body">
    <Transition enter-active-class="transition duration-200" enter-from-class="opacity-0" leave-active-class="transition duration-150" leave-to-class="opacity-0">
      <div v-if="open" class="fixed inset-0 z-[100] flex cursor-pointer items-end justify-center bg-slate-950/90 pt-4 sm:grid sm:place-items-center sm:p-4" role="presentation" @click.self="emit('close')">
        <section role="dialog" aria-modal="true" aria-labelledby="adult-modal-title" aria-describedby="adult-modal-description" class="max-h-[calc(100dvh-1rem)] w-full max-w-md cursor-default overflow-y-auto rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] text-ink shadow-2xl shadow-black/40 ring-1 ring-line sm:rounded-3xl sm:pb-0">
          <div class="border-b border-crimson/30 bg-wine p-5 sm:p-6">
            <span class="crimson-glow grid h-12 w-12 place-items-center rounded-2xl bg-crimson text-ink"><span class="text-lg font-black">۱۸+</span></span>
            <p class="mt-4 text-xs font-black text-coral-300">مناسب بزرگسالان</p>
            <h2 id="adult-modal-title" class="mt-1 text-xl font-black text-ink">تأیید مشاهده محتوا</h2>
            <p v-if="title" class="mt-1 text-sm font-bold text-secondary">{{ title }}</p>
          </div>
          <div class="p-5 sm:p-6">
            <p id="adult-modal-description" class="text-sm leading-7 text-secondary">این عنوان در رده سنی بزرگسال قرار دارد و ممکن است برای همه مناسب نباشد. برای ادامه، تأیید کنید.</p>
            <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row">
              <button type="button" class="ui-secondary-button flex-1" @click="emit('close')">بازگشت</button>
              <button ref="confirmButton" type="button" class="min-h-12 flex-1 rounded-xl bg-primary-500 px-4 py-3 text-sm font-black text-night-950 shadow-sm transition hover:bg-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2" @click="emit('confirm')">ادامه پخش</button>
            </div>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
