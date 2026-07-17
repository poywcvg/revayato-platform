<script setup lang="ts">
import type { Genre } from '~/types'

const props = withDefaults(defineProps<{
  genres: Genre[]
  modelValue?: string
  allLabel?: string
  compact?: boolean
}>(), {
  modelValue: '',
  allLabel: 'همه ژانرها',
  compact: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const showAll = ref(false)
const visibleCount = 5

const limitedGenres = computed(() =>
  showAll.value ? props.genres : props.genres.slice(0, visibleCount),
)

function selectGenre(slug: string) {
  emit('update:modelValue', slug)
}
</script>

<template>
  <div v-if="compact" class="min-w-0">
    <GenreSelect
      :genres="genres"
      :model-value="modelValue"
      :all-label="allLabel"
      compact
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
  <div v-else class="flex items-start gap-2">
    <div class="hide-scrollbar flex flex-1 gap-2 overflow-x-auto pb-1" role="group" aria-label="فیلتر ژانر">
      <button type="button" class="min-h-11 shrink-0 rounded-xl px-4 py-2.5 text-sm font-bold transition" :class="!modelValue ? 'cinema-glow bg-primary-500 text-night-950' : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'" @click="selectGenre('')">{{ allLabel }}</button>
      <button v-for="genre in limitedGenres" :key="genre.id" type="button" class="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition" :class="modelValue === genre.slug ? 'cinema-glow bg-primary-500 text-night-950' : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'" @click="selectGenre(genre.slug)">
        <CinematicIcon :name="genre.icon" class="size-4" />{{ genre.title }}
      </button>
    </div>
    <div v-if="genres.length > visibleCount" class="shrink-0">
      <button
        type="button"
        class="inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-elevated px-3 py-2.5 text-xs font-bold text-secondary ring-1 ring-line transition hover:text-primary-300 hover:ring-primary-500/40"
        @click="showAll = !showAll"
      >
        <CinematicIcon :name="showAll ? 'chevron-up' : 'chevron-down'" class="size-4" />
        <span class="hidden sm:inline">{{ showAll ? 'کمتر' : `${genres.length} ژانر` }}</span>
      </button>
    </div>
  </div>
</template>
