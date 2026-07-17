<script setup lang="ts">
import type { PlaybackQuality } from '~/types'

const props = withDefaults(defineProps<{
  audioLanguages?: string[]
  subtitleLanguages?: string[]
  hasNextEpisode?: boolean
}>(), {
  audioLanguages: () => ['دوبله فارسی', 'زبان اصلی'],
  subtitleLanguages: () => ['فارسی'],
  hasNextEpisode: false,
})

const emit = defineEmits<{
  skipIntro: []
  nextEpisode: []
  audioChange: [value: string]
  subtitleChange: [value: string]
  qualityChange: [value: PlaybackQuality]
}>()

const audio = ref(props.audioLanguages[0] || 'زبان اصلی')
const subtitle = ref(props.subtitleLanguages[0] || 'خاموش')
const quality = ref<PlaybackQuality>('auto')
const audioOptions = computed(() => props.audioLanguages.map(item => ({ value: item, label: `صدا: ${item}` })))
const subtitleOptions = computed(() => [
  { value: 'خاموش', label: 'زیرنویس: خاموش' },
  ...props.subtitleLanguages.map(item => ({ value: item, label: `زیرنویس: ${item}` })),
])
const qualityOptions: Array<{ value: PlaybackQuality; label: string; description: string }> = [
  { value: 'auto', label: 'کیفیت خودکار', description: 'تنظیم هوشمند بر اساس سرعت اینترنت' },
  { value: '1080p', label: '1080p', description: 'Full HD · مصرف داده بیشتر' },
  { value: '720p', label: '720p', description: 'HD · تعادل کیفیت و مصرف' },
  { value: '480p', label: '480p', description: 'مناسب اینترنت کم‌سرعت' },
]

watch(() => props.audioLanguages, (languages) => {
  if (!languages.includes(audio.value)) audio.value = languages[0] || 'زبان اصلی'
})

watch(() => props.subtitleLanguages, (languages) => {
  if (subtitle.value !== 'خاموش' && !languages.includes(subtitle.value)) subtitle.value = languages[0] || 'خاموش'
})

function handleAudioChange(value: string | number) {
  emit('audioChange', String(value))
}

function handleSubtitleChange(value: string | number) {
  emit('subtitleChange', String(value))
}

function handleQualityChange(value: string | number) {
  emit('qualityChange', value as PlaybackQuality)
}
</script>

<template>
  <section class="mt-3 rounded-2xl bg-white/[.04] p-3 ring-1 ring-white/10 sm:p-4" aria-label="تنظیمات پخش">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <div class="col-span-2 min-w-0 sm:col-auto sm:min-w-44"><UiSelect v-model="audio" :options="audioOptions" label="صدای پخش" icon="audio" compact @change="handleAudioChange" /></div>
        <div class="min-w-0 sm:min-w-40"><UiSelect v-model="subtitle" :options="subtitleOptions" label="زیرنویس" icon="subtitle" compact @change="handleSubtitleChange" /></div>
        <div class="min-w-0 sm:min-w-40"><UiSelect v-model="quality" :options="qualityOptions" label="کیفیت پخش" icon="quality" compact @change="handleQualityChange" /></div>
      </div>

      <div class="grid grid-cols-2 gap-2 sm:flex">
        <button type="button" class="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl bg-white/5 px-3 text-xs font-black text-slate-300 ring-1 ring-white/10 transition hover:bg-white/10 hover:text-white" @click="emit('skipIntro')">
          <CinematicIcon name="fast-forward" class="size-4" />رد کردن تیتراژ
        </button>
        <button v-if="hasNextEpisode" type="button" class="cinema-glow inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl bg-primary-500 px-4 text-xs font-black text-night-950 transition hover:bg-primary-400" @click="emit('nextEpisode')">
          قسمت بعدی<CinematicIcon name="chevron-left" class="size-4" />
        </button>
      </div>
    </div>
  </section>
</template>
