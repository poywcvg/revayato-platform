<script setup lang="ts">
withDefaults(defineProps<{
  id: string
  label?: string
  autocomplete?: string
  showStrength?: boolean
  required?: boolean
}>(), {
  label: 'رمز عبور',
  autocomplete: 'current-password',
  showStrength: false,
  required: true,
})

const model = defineModel<string>({ required: true })
const visible = ref(false)
const checks = computed(() => [
  model.value.length >= 8,
  /[A-Za-z\u0600-\u06ff]/.test(model.value),
  /\d/.test(model.value),
  model.value.length >= 12 || /[^A-Za-z0-9\u0600-\u06ff]/.test(model.value),
])
const score = computed(() => checks.value.filter(Boolean).length)
const strength = computed(() => [
  { label: 'خیلی ضعیف', color: 'bg-error' },
  { label: 'ضعیف', color: 'bg-error' },
  { label: 'قابل قبول', color: 'bg-warning' },
  { label: 'خوب', color: 'bg-primary-500' },
  { label: 'قوی', color: 'bg-success' },
][score.value] || { label: 'خیلی ضعیف', color: 'bg-error' })
</script>

<template>
  <div>
    <label v-if="label" :for="id" class="mb-1.5 block text-sm font-bold text-secondary">{{ label }}</label>
    <div class="relative">
      <input :id="id" v-model="model" :type="visible ? 'text' : 'password'" :autocomplete="autocomplete" :required="required" minlength="8" class="ui-field px-4 pl-12 text-sm">
      <button type="button" class="absolute inset-y-1 left-1 grid w-10 place-items-center rounded-lg text-muted hover:bg-elevated hover:text-ink" :aria-label="visible ? 'پنهان کردن رمز عبور' : 'نمایش رمز عبور'" :aria-pressed="visible" @click="visible = !visible"><CinematicIcon :name="visible ? 'eye-off' : 'eye'" class="size-4.5" /></button>
    </div>
    <div v-if="showStrength && model" class="mt-2" aria-live="polite">
      <div class="grid grid-cols-4 gap-1" aria-hidden="true"><span v-for="index in 4" :key="index" class="h-1 rounded-full" :class="index <= score ? strength.color : 'bg-elevated'" /></div>
      <div class="mt-1.5 flex items-center justify-between gap-3 text-[11px]"><span class="text-muted">حداقل ۸ کاراکتر همراه حرف و عدد</span><span class="font-black" :class="score >= 4 ? 'text-success' : score >= 2 ? 'text-warning' : 'text-error'">{{ strength.label }}</span></div>
    </div>
  </div>
</template>
