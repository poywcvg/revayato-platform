<script setup lang="ts">
import type { SiteActor } from '~/types'

defineProps<{
  actor: SiteActor
  priority?: boolean
}>()
</script>

<template>
  <article class="cinematic-card group min-w-0 overflow-hidden rounded-2xl">
    <NuxtLink :to="`/actors/${actor.slug}`" class="block text-center" :aria-label="`صفحه ${actor.name}`">
      <div class="cinematic-media relative aspect-[3/4] overflow-hidden">
        <NuxtImg
          v-if="actor.photo"
          :src="actor.photo"
          :alt="actor.name"
          class="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
          :loading="priority ? 'eager' : 'lazy'"
          sizes="(max-width: 639px) 45vw, (max-width: 1023px) 22vw, 180px"
        />
        <span
          v-else
          class="theme-media-dark grid h-full w-full place-items-center bg-gradient-to-br from-primary-600 to-primary-900 text-3xl font-black text-white"
        >{{ actor.name.slice(0, 1) }}</span>
      </div>
      <div class="p-3">
        <h3 class="truncate text-sm font-black text-ink" dir="auto">{{ actor.name }}</h3>
        <p v-if="actor.secondary_name" class="mt-0.5 truncate text-xs text-secondary" dir="rtl">{{ actor.secondary_name }}</p>
        <p v-if="actor.birth_place" class="mt-0.5 truncate text-xs text-muted">{{ actor.birth_place }}</p>
      </div>
    </NuxtLink>
  </article>
</template>
