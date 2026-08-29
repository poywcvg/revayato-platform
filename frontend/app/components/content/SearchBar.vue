<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  large?: boolean
  loading?: boolean
}>(), {
  placeholder: 'جستجوی فیلم یا سریال...',
  large: false,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  focus: [event: FocusEvent]
  blur: [event: FocusEvent]
  submit: []
}>()

const input = useTemplateRef<HTMLInputElement>('input')

defineExpose({
  focus: () => input.value?.focus(),
})
</script>

<template>
  <label class="relative block">
    <span class="sr-only">جستجو</span>
    <CinematicIcon name="search" class="pointer-events-none absolute right-4 top-1/2 size-5 -translate-y-1/2 text-brand" />
    <input
      ref="input"
      :value="modelValue"
      type="search"
      :placeholder="placeholder"
      class="ui-field pr-12 pl-11 placeholder:text-muted"
      :class="large ? 'h-14 rounded-2xl text-base' : 'h-12 text-sm'"
      enterkeyhint="search"
      autocomplete="off"
      spellcheck="false"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      @focus="emit('focus', $event)"
      @blur="emit('blur', $event)"
      @keydown.enter.prevent="emit('submit')"
    >
    <span v-if="loading && modelValue" class="absolute left-4 top-1/2 -translate-y-1/2">
      <CinematicIcon name="refresh" class="size-4 animate-spin text-brand" />
    </span>
    <button v-else-if="modelValue" type="button" class="absolute left-1 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-lg text-muted transition-colors hover:bg-primary-500/10 hover:text-brand" aria-label="پاک کردن جستجو" @click="emit('update:modelValue', '')"><CinematicIcon name="x" class="size-4" /></button>
  </label>
</template>
