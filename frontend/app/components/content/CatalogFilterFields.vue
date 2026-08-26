<script setup lang="ts">
import type { CinematicIconName, Genre } from '~/types'
import type { CatalogFilters } from '~/composables/content/useContent'

interface FilterSelectOption {
  value: string
  label: string
  description?: string
}

type FilterFieldKey =
  | 'country'
  | 'year'
  | 'ageRating'
  | 'language'
  | 'availability'
  | 'format'
  | 'minRating'
  | 'genre'

interface SelectGroup {
  key: Extract<FilterFieldKey, 'country' | 'year' | 'ageRating' | 'language'>
  label: string
  icon?: CinematicIconName
}

interface SelectRow {
  key: Extract<FilterFieldKey, 'availability' | 'format' | 'minRating'>
  label: string
  icon?: CinematicIconName
}

defineProps<{
  filters: CatalogFilters
  genres: Genre[]
  countryOptions: readonly FilterSelectOption[]
  yearOptions: readonly FilterSelectOption[]
  languageOptions: readonly FilterSelectOption[]
  ageRatingOptions: readonly FilterSelectOption[]
  availabilityOptions: readonly FilterSelectOption[]
  formatOptions: readonly FilterSelectOption[]
  ratingOptions: readonly FilterSelectOption[]
}>()

const emit = defineEmits<{
  change: [key: FilterFieldKey, value: string]
}>()

const mainGroups: SelectGroup[] = [
  { key: 'country', label: 'کشور سازنده', icon: 'globe' },
  { key: 'year', label: 'سال انتشار', icon: 'calendar' },
  { key: 'ageRating', label: 'رده سنی', icon: 'shield-check' },
  { key: 'language', label: 'زبان محتوا', icon: 'globe' },
]
const detailRows: SelectRow[] = [
  { key: 'availability', label: 'نسخه پخش', icon: 'play' },
  { key: 'format', label: 'فرمت', icon: 'clapperboard' },
  { key: 'minRating', label: 'حداقل امتیاز IMDb', icon: 'star' },
]

function onSelect(key: FilterFieldKey) {
  return (value: unknown) => emit('change', key, String(value))
}
</script>

<template>
  <div class="grid gap-3 p-3 sm:grid-cols-2 sm:p-4 xl:grid-cols-4">
    <div v-for="group in mainGroups" :key="group.key">
      <span class="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold text-muted">
        <CinematicIcon v-if="group.icon" :name="group.icon" class="size-3.5" />{{ group.label }}
      </span>
      <UiSelect
        :model-value="filters[group.key]"
        :options="
          group.key === 'country' ? countryOptions
          : group.key === 'year' ? yearOptions
          : group.key === 'ageRating' ? ageRatingOptions
          : languageOptions
        "
        :label="group.label"
        compact
        @update:model-value="onSelect(group.key)"
      />
    </div>
    <div v-for="row in detailRows" :key="row.key">
      <span class="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold text-muted"><CinematicIcon v-if="row.icon" :name="row.icon" class="size-3.5" />{{ row.label }}</span>
      <UiSelect :model-value="filters[row.key]" :options="row.key === 'availability' ? availabilityOptions : row.key === 'format' ? formatOptions : ratingOptions" :label="row.label" compact @update:model-value="onSelect(row.key)" />
    </div>
    <div class="sm:col-span-2 xl:col-span-4">
      <p class="mb-2 flex items-center gap-1.5 text-[11px] font-bold text-muted">
        <CinematicIcon name="tag" class="size-3.5" />ژانر
      </p>
      <GenreChips
        :model-value="filters.genre"
        :genres="genres"
        all-label="همه ژانرها"
        compact
        @update:model-value="emit('change', 'genre', $event)"
      />
    </div>
  </div>
</template>
