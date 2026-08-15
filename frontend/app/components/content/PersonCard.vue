<script setup lang="ts">
const props = withDefaults(defineProps<{
  name: string
  secondaryName?: string
  photoUrl?: string | null
  slug?: string
  kind: 'actor' | 'director'
  /** Character name for actors, or job label for crew. */
  caption?: string
}>(), {
  secondaryName: '',
  photoUrl: null,
  slug: '',
  caption: '',
})

const emit = defineEmits<{
  select: []
}>()

const href = computed(() => {
  if (props.kind !== 'actor' || !props.slug) return ''
  return `/actors/${props.slug}`
})

const fallbackTone = computed(() => props.kind === 'director'
  ? 'from-amber-400/80 to-night-800 text-night-950'
  : 'from-white/20 to-night-800 text-white/80')
</script>

<template>
  <NuxtLink
    v-if="href"
    :to="href"
    class="person-chip group"
    :aria-label="name"
    @click="emit('select')"
  >
    <span class="person-chip__photo" aria-hidden="true">
      <NuxtImg
        v-if="photoUrl"
        :src="photoUrl"
        :alt="''"
        class="h-full w-full object-cover transition duration-300 group-hover:scale-[1.04]"
        loading="lazy"
        sizes="96px"
      />
      <span
        v-else
        class="grid h-full w-full place-items-center bg-gradient-to-br text-base font-black"
        :class="fallbackTone"
      >{{ name.slice(0, 1) }}</span>
    </span>
    <span class="person-chip__meta">
      <span class="person-chip__name" dir="auto">{{ name }}</span>
      <span v-if="secondaryName" class="person-chip__secondary" dir="rtl">{{ secondaryName }}</span>
      <span v-if="caption" class="person-chip__caption">{{ caption }}</span>
    </span>
  </NuxtLink>

  <button
    v-else
    type="button"
    class="person-chip group"
    :aria-label="name"
    @click="emit('select')"
  >
    <span class="person-chip__photo" aria-hidden="true">
      <NuxtImg
        v-if="photoUrl"
        :src="photoUrl"
        :alt="''"
        class="h-full w-full object-cover transition duration-300 group-hover:scale-[1.04]"
        loading="lazy"
        sizes="96px"
      />
      <span
        v-else
        class="grid h-full w-full place-items-center bg-gradient-to-br text-base font-black"
        :class="fallbackTone"
      >{{ name.slice(0, 1) }}</span>
    </span>
    <span class="person-chip__meta">
      <span class="person-chip__name" dir="auto">{{ name }}</span>
      <span v-if="secondaryName" class="person-chip__secondary" dir="rtl">{{ secondaryName }}</span>
      <span v-if="caption" class="person-chip__caption">{{ caption }}</span>
    </span>
  </button>
</template>

<style scoped>
.person-chip {
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 2.75rem;
  align-items: center;
  gap: .75rem;
  padding: .35rem .15rem;
  text-align: right;
  transition: opacity .15s ease;
}

.person-chip:focus-visible {
  border-radius: .75rem;
  outline: 2px solid var(--theme-accent-primary);
  outline-offset: 2px;
}

.person-chip__photo {
  display: block;
  width: 3.25rem;
  height: 3.25rem;
  flex: none;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(15 23 42);
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 10%);
}

.person-chip__meta {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: .1rem;
}

.person-chip__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: .8125rem;
  font-weight: 800;
  color: rgb(248 250 252);
}

.person-chip__secondary,
.person-chip__caption {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: .6875rem;
  font-weight: 600;
  color: rgb(148 163 184);
}

.person-chip__caption {
  color: rgb(100 116 139);
}

@media (min-width: 640px) {
  .person-chip {
    flex-direction: column;
    align-items: center;
    gap: .55rem;
    padding: .25rem;
    text-align: center;
  }

  .person-chip__photo {
    width: 4.5rem;
    height: 4.5rem;
  }

  .person-chip__meta {
    justify-items: center;
  }
}

@media (hover: hover) and (pointer: fine) {
  .person-chip:hover {
    opacity: .92;
  }
}
</style>
