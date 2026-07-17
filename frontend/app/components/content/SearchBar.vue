<script setup lang="ts">
withDefaults(defineProps<{ modelValue: string; placeholder?: string; large?: boolean }>(), { placeholder: 'جستجوی فیلم یا سریال...', large: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <label class="relative block">
    <span class="sr-only">جستجو</span>
    <CinematicIcon name="search" class="pointer-events-none absolute right-4 top-1/2 size-5 -translate-y-1/2 text-primary-600" />
    <input :value="modelValue" type="search" :placeholder="placeholder" class="ui-field pr-12 pl-11 placeholder:text-slate-400" :class="large ? 'rounded-2xl py-4 text-base shadow-sm' : 'py-3 text-sm'" @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)">
    <button v-if="modelValue" type="button" class="absolute left-1.5 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-lg text-muted transition-colors hover:bg-primary-500/10 hover:text-primary-300" aria-label="پاک کردن جستجو" @click="emit('update:modelValue', '')"><CinematicIcon name="x" class="size-4" /></button>
  </label>
</template>
