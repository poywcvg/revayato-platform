<script setup lang="ts">
import type { CinematicIconName } from '~/types'

const moods: Array<{ value: string; label: string; icon: CinematicIconName; color: string }> = [
  { value: 'exciting', label: 'هیجان‌انگیز', icon: 'exciting', color: 'bg-primary-500/10' },
  { value: 'calm', label: 'آرام', icon: 'calm', color: 'bg-elevated' },
  { value: 'scary', label: 'ترسناک', icon: 'scary', color: 'bg-error/[.07]' },
  { value: 'romantic', label: 'عاشقانه', icon: 'heart', color: 'bg-primary-500/[.07]' },
  { value: 'thoughtful', label: 'فکری', icon: 'thoughtful', color: 'bg-surface' },
  { value: 'family', label: 'خانوادگی', icon: 'family', color: 'bg-elevated' },
  { value: 'light', label: 'کوتاه و سبک', icon: 'light', color: 'bg-primary-500/[.06]' },
]

defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <section class="content-section">
    <div class="ui-surface relative overflow-hidden p-5 sm:p-7">
      <SectionHeader title="امشب چی ببینم؟" eyebrow="انتخاب بر اساس حال‌وهوای تو" description="یک حس را انتخاب کن تا پیشنهادهای مناسب همین لحظه مرتب شوند." icon="mood" />
      <div class="mood-grid relative grid gap-2.5">
        <button v-for="mood in moods" :key="mood.value" type="button" class="group relative min-h-24 overflow-hidden rounded-2xl p-3 text-right ring-1 ring-inset transition hover:-translate-y-0.5" :class="[mood.color, modelValue === mood.value ? 'cinema-glow ring-primary-400' : 'ring-line hover:ring-primary-500/35']" :aria-pressed="modelValue === mood.value" @click="emit('update:modelValue', modelValue === mood.value ? '' : mood.value)"><span class="grid size-9 place-items-center rounded-xl ring-1 transition" :class="modelValue === mood.value ? 'bg-primary-500 text-night-950 ring-primary-400' : 'bg-surface text-secondary ring-line group-hover:bg-primary-500/14 group-hover:text-brand'"><CinematicIcon :name="mood.icon" class="size-5" :filled="modelValue === mood.value && mood.icon === 'heart'" /></span><span class="mt-3 block text-xs font-black text-ink">{{ mood.label }}</span></button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.mood-grid {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 7.25rem), 1fr));
}
</style>
