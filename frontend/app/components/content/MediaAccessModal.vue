<script setup lang="ts">
import type { DownloadLink } from '~/types'
import type { DownloadPlayRequest } from '~/components/content/DownloadBox.vue'

const props = defineProps<{
  open: boolean
  mode: 'play' | 'download'
  links: DownloadLink[]
  title: string
  slug?: string
  accentStyle?: Record<string, string>
}>()

const emit = defineEmits<{
  close: []
  play: [request: DownloadPlayRequest]
}>()

const panel = useTemplateRef<HTMLElement>('panel')
const closeButton = useTemplateRef<HTMLButtonElement>('closeButton')
let previouslyFocused: HTMLElement | null = null
let previousRootOverflow = ''

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

const modalTitle = computed(() => (
  props.mode === 'play' ? 'انتخاب نسخه پخش آنلاین' : 'انتخاب لینک دانلود'
))

const modalDescription = computed(() => (
  props.mode === 'play'
    ? 'نسخه، کیفیت یا قسمت موردنظر را برای تماشا انتخاب کن.'
    : 'نسخه، کیفیت یا قسمت موردنظر را برای دانلود انتخاب کن.'
))

function close() {
  emit('close')
}

function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !panel.value) return
  const controls = [...panel.value.querySelectorAll<HTMLElement>(focusableSelector)]
    .filter(control => control.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)
  if (!first || !last) {
    event.preventDefault()
    panel.value.focus()
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
  if (open) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    previousRootOverflow = document.documentElement.style.overflow
    document.documentElement.style.overflow = 'hidden'
    await nextTick()
    closeButton.value?.focus()
    return
  }

  document.documentElement.style.overflow = previousRootOverflow
  previouslyFocused?.focus()
  previouslyFocused = null
}, { immediate: true })

onKeyStroke('Escape', () => {
  if (props.open) close()
})

onBeforeUnmount(() => {
  if (!import.meta.client) return
  document.documentElement.style.overflow = previousRootOverflow
})
</script>

<template>
  <Teleport to="body">
    <Transition name="media-access-modal">
      <div
        v-if="open"
        class="media-access-modal theme-media-dark"
        role="presentation"
        @mousedown.self="close"
      >
        <section
          ref="panel"
          tabindex="-1"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="`media-access-title-${mode}`"
          :aria-describedby="`media-access-description-${mode}`"
          class="media-access-modal__panel"
          :data-mode="mode"
          :style="accentStyle"
          @keydown="trapFocus"
        >
          <header class="media-access-modal__head">
            <span class="media-access-modal__icon" aria-hidden="true">
              <CinematicIcon :name="mode === 'play' ? 'play' : 'download'" class="size-5" :filled="mode === 'play'" />
            </span>
            <div class="min-w-0 flex-1">
              <h2 :id="`media-access-title-${mode}`" class="media-access-modal__title">
                {{ modalTitle }}
              </h2>
              <p class="media-access-modal__media-title" dir="auto">{{ title }}</p>
              <p :id="`media-access-description-${mode}`" class="media-access-modal__description">
                {{ modalDescription }}
              </p>
            </div>
            <button
              ref="closeButton"
              type="button"
              class="media-access-modal__close"
              aria-label="بستن پنجره"
              @click="close"
            >
              <CinematicIcon name="x" class="size-5" />
            </button>
          </header>

          <div class="media-access-modal__body">
            <DownloadBox
              :links="links"
              :slug="slug"
              :mode="mode"
              @play="emit('play', $event)"
            />
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.media-access-modal {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: flex;
  cursor: pointer;
  align-items: flex-end;
  justify-content: center;
  padding-top: max(.75rem, env(safe-area-inset-top));
  background: rgb(2 6 5 / 84%);
  backdrop-filter: blur(7px);
}

.media-access-modal__panel {
  --page-bg: #050807;
  --surface-1: #0a1210;
  --surface-2: #0f1916;
  --surface-3: #16241f;
  --text-primary: #e6ebe9;
  --text-secondary: #a7b2ad;
  --text-muted: #7a8681;
  --border-color: rgb(255 255 255 / 10%);
  --theme-bg-main: #050807;
  --theme-bg-soft: #08100e;
  --theme-bg-surface: #0a1210;
  --theme-bg-elevated: #0f1916;
  --theme-border: rgb(255 255 255 / 10%);
  --theme-text-primary: #e6ebe9;
  --theme-text-secondary: #a7b2ad;
  --theme-text-muted: #7a8681;
  --theme-text-disabled: #56605c;
  width: min(100%, 58rem);
  max-height: calc(100dvh - max(.75rem, env(safe-area-inset-top)));
  overflow: hidden;
  cursor: default;
  border: 1px solid rgb(255 255 255 / 11%);
  border-bottom: 0;
  border-radius: 1.5rem 1.5rem 0 0;
  color: var(--text-primary);
  background:
    radial-gradient(circle at 80% -20%, rgb(var(--media-accent-rgb, 176 228 204) / 20%), transparent 42%),
    #07100d;
  box-shadow: 0 -24px 70px rgb(0 0 0 / 55%);
  outline: none;
}

.media-access-modal__panel[data-mode='download'] {
  background:
    radial-gradient(circle at 80% -20%, rgb(245 165 36 / 18%), transparent 42%),
    #100d08;
}

.media-access-modal__head {
  display: flex;
  align-items: flex-start;
  gap: .8rem;
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
}

@media (max-width: 639px) {
  .media-access-modal__panel {
    max-height: calc(100dvh - max(.5rem, env(safe-area-inset-top)));
    border-radius: 1.2rem 1.2rem 0 0;
  }

  .media-access-modal__head {
    gap: .55rem;
    padding: .8rem .85rem;
  }

  .media-access-modal__icon,
  .media-access-modal__close {
    width: 2.45rem;
    height: 2.45rem;
    border-radius: .75rem;
  }

  .media-access-modal__title {
    font-size: .92rem;
  }

  .media-access-modal__media-title {
    font-size: .74rem;
  }

  .media-access-modal__description {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-size: .65rem;
  }

  .media-access-modal__body {
    max-height: calc(100dvh - 7.6rem - max(.5rem, env(safe-area-inset-top)) - env(safe-area-inset-bottom));
    padding: .45rem .45rem calc(.55rem + env(safe-area-inset-bottom));
  }
}

.media-access-modal__icon,
.media-access-modal__close {
  display: grid;
  width: 2.75rem;
  height: 2.75rem;
  flex: none;
  place-items: center;
  border-radius: .9rem;
}

.media-access-modal__icon {
  color: #050807;
  background: var(--media-accent, #b0e4cc);
}

[data-mode='download'] .media-access-modal__icon {
  color: #2b1700;
  background: #f5a524;
}

.media-access-modal__close {
  color: var(--text-secondary);
  background: rgb(255 255 255 / 6%);
  border: 1px solid rgb(255 255 255 / 10%);
  transition: color .15s ease, background .15s ease, border-color .15s ease;
}

.media-access-modal__close:hover {
  color: white;
  background: rgb(255 255 255 / 11%);
  border-color: rgb(255 255 255 / 18%);
}

.media-access-modal__close:focus-visible {
  outline: 2px solid var(--media-accent, #b0e4cc);
  outline-offset: 2px;
}

.media-access-modal__title {
  font-size: 1rem;
  font-weight: 900;
}

.media-access-modal__media-title {
  margin-top: .15rem;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: .8rem;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.media-access-modal__description {
  margin-top: .3rem;
  color: var(--text-muted);
  font-size: .7rem;
  line-height: 1.55;
}

.media-access-modal__body {
  max-height: calc(100dvh - 8.9rem - max(.75rem, env(safe-area-inset-top)) - env(safe-area-inset-bottom));
  overflow-y: auto;
  padding: .65rem .65rem calc(.65rem + env(safe-area-inset-bottom));
  overscroll-behavior: contain;
}

@media (min-width: 640px) {
  .media-access-modal {
    align-items: center;
    padding: 1.25rem;
  }

  .media-access-modal__panel {
    max-height: calc(100dvh - 2.5rem);
    border-bottom: 1px solid rgb(255 255 255 / 11%);
    border-radius: 1.5rem;
  }

  .media-access-modal__head {
    padding: 1.15rem 1.25rem;
  }

  .media-access-modal__title {
    font-size: 1.15rem;
  }

  .media-access-modal__body {
    max-height: calc(100dvh - 10rem);
    padding: .8rem;
  }
}

.media-access-modal-enter-active,
.media-access-modal-leave-active {
  transition: opacity .18s ease;
}

.media-access-modal-enter-active .media-access-modal__panel,
.media-access-modal-leave-active .media-access-modal__panel {
  transition: transform .2s ease, opacity .18s ease;
}

.media-access-modal-enter-from,
.media-access-modal-leave-to {
  opacity: 0;
}

.media-access-modal-enter-from .media-access-modal__panel,
.media-access-modal-leave-to .media-access-modal__panel {
  opacity: 0;
  transform: translateY(1rem) scale(.985);
}

@media (prefers-reduced-motion: reduce) {
  .media-access-modal-enter-active,
  .media-access-modal-leave-active,
  .media-access-modal-enter-active .media-access-modal__panel,
  .media-access-modal-leave-active .media-access-modal__panel {
    transition: none;
  }
}
</style>
