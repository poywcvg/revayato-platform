<script setup lang="ts" generic="T extends string | number">
import type { CinematicIconName } from '~/types'

export interface UiSelectOption<Value extends string | number = string> {
  value: Value
  label: string
  description?: string
}

const props = withDefaults(defineProps<{
  modelValue: T
  options: readonly UiSelectOption<T>[]
  label: string
  icon?: CinematicIconName
  compact?: boolean
  disabled?: boolean
}>(), {
  icon: undefined,
  compact: false,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: T]
  change: [value: T]
}>()

const root = useTemplateRef<HTMLElement>('root')
const trigger = useTemplateRef<HTMLButtonElement>('trigger')
const menu = useTemplateRef<HTMLElement>('menu')
const instanceId = useId()
const isOpen = ref(false)
const openAbove = ref(false)
const activeIndex = ref(0)

const selectedIndex = computed(() => {
  const index = props.options.findIndex(option => option.value === props.modelValue)
  return index >= 0 ? index : 0
})
const selectedOption = computed(() => props.options[selectedIndex.value])

function optionId(index: number) {
  return `${instanceId}-option-${index}`
}

function scrollActiveOptionIntoView() {
  nextTick(() => {
    const list = menu.value
    const option = document.getElementById(optionId(activeIndex.value))
    if (!list || !option) return
    const optionTop = option.offsetTop
    const optionBottom = optionTop + option.offsetHeight
    if (optionTop < list.scrollTop) list.scrollTop = optionTop
    else if (optionBottom > list.scrollTop + list.clientHeight) list.scrollTop = optionBottom - list.clientHeight
  })
}

function openMenu() {
  if (props.disabled || !props.options.length) return
  const rect = trigger.value?.getBoundingClientRect()
  openAbove.value = Boolean(rect && rect.bottom + 310 > window.innerHeight && rect.top > 310)
  activeIndex.value = selectedIndex.value
  isOpen.value = true
  scrollActiveOptionIntoView()
}

function closeMenu({ restoreFocus = false } = {}) {
  if (!isOpen.value) return
  isOpen.value = false
  if (restoreFocus) nextTick(() => trigger.value?.focus())
}

function toggleMenu() {
  if (isOpen.value) closeMenu()
  else openMenu()
}

function moveActive(step: number) {
  if (!props.options.length) return
  activeIndex.value = (activeIndex.value + step + props.options.length) % props.options.length
  scrollActiveOptionIntoView()
}

function choose(option: UiSelectOption<T>) {
  if (option.value !== props.modelValue) {
    emit('update:modelValue', option.value)
    emit('change', option.value)
  }
  closeMenu({ restoreFocus: true })
}

function handleKeydown(event: KeyboardEvent) {
  if (props.disabled) return

  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!isOpen.value) openMenu()
    else moveActive(event.key === 'ArrowDown' ? 1 : -1)
    return
  }

  if (event.key === 'Home' || event.key === 'End') {
    if (!isOpen.value) return
    event.preventDefault()
    activeIndex.value = event.key === 'Home' ? 0 : props.options.length - 1
    scrollActiveOptionIntoView()
    return
  }

  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!isOpen.value) openMenu()
    else {
      const option = props.options[activeIndex.value]
      if (option) choose(option)
    }
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    closeMenu({ restoreFocus: true })
  }
}

onClickOutside(root, () => closeMenu())
watch(() => props.modelValue, () => {
  activeIndex.value = selectedIndex.value
})
</script>

<template>
  <div ref="root" class="ui-select" :class="isOpen && 'ui-select--open'">
    <button
      :id="`${instanceId}-trigger`"
      ref="trigger"
      type="button"
      role="combobox"
      class="ui-select__trigger"
      :class="compact ? 'ui-select__trigger--compact' : ''"
      :aria-label="label"
      :aria-expanded="isOpen"
      :aria-controls="`${instanceId}-listbox`"
      :aria-activedescendant="isOpen ? optionId(activeIndex) : undefined"
      aria-haspopup="listbox"
      :disabled="disabled"
      @click="toggleMenu"
      @keydown="handleKeydown"
    >
      <span v-if="icon" class="ui-select__leading" aria-hidden="true"><CinematicIcon :name="icon" class="size-4" /></span>
      <span class="min-w-0 flex-1 truncate text-right">{{ selectedOption?.label || 'انتخاب کنید' }}</span>
      <CinematicIcon name="chevron-down" class="ui-select__chevron size-4" :class="isOpen && 'rotate-180'" aria-hidden="true" />
    </button>

    <Transition name="ui-dropdown">
      <div
        v-if="isOpen"
        :id="`${instanceId}-listbox`"
        ref="menu"
        role="listbox"
        class="ui-select__menu soft-scrollbar"
        :class="openAbove ? 'ui-select__menu--above' : 'ui-select__menu--below'"
        :aria-labelledby="`${instanceId}-trigger`"
      >
        <div class="ui-select__menu-head" aria-hidden="true"><span />{{ label }}</div>
        <button
          v-for="(option, index) in options"
          :id="optionId(index)"
          :key="String(option.value)"
          type="button"
          role="option"
          class="ui-select__option"
          :class="[
            option.value === modelValue && 'ui-select__option--selected',
            index === activeIndex && 'ui-select__option--active',
          ]"
          :aria-selected="option.value === modelValue"
          @mouseenter="activeIndex = index"
          @click="choose(option)"
        >
          <span class="ui-select__option-mark"><CinematicIcon v-if="option.value === modelValue" name="check" class="size-3.5" /></span>
          <span class="min-w-0 flex-1 text-right">
            <strong class="block truncate text-xs">{{ option.label }}</strong>
            <span v-if="option.description" class="mt-0.5 block truncate text-[10px] text-muted">{{ option.description }}</span>
          </span>
        </button>
      </div>
    </Transition>
  </div>
</template>
