<script setup lang="ts">
import AlertCircle from '~icons/lucide/circle-alert'
import Film from '~icons/lucide/film'

withDefaults(defineProps<{ kind?: 'empty' | 'error'; title: string; message: string }>(), { kind: 'empty' })
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="grid min-h-72 place-items-center px-5 py-12 text-center">
    <div class="max-w-md">
      <span
        class="mx-auto grid size-14 place-items-center rounded-2xl"
        :class="kind === 'error' ? 'bg-red-50 text-[var(--admin-danger)]' : 'bg-[var(--admin-surface-muted)] text-[var(--admin-accent)]'"
      >
        <AlertCircle v-if="kind === 'error'" class="size-6" />
        <Film v-else class="size-6" />
      </span>
      <h3 class="mt-4 text-base font-black">{{ title }}</h3>
      <p class="mt-2 text-sm leading-7 text-[var(--admin-muted)]">{{ message }}</p>
      <div v-if="$slots.default || kind === 'error'" class="mt-5">
        <slot>
          <AdminButton variant="secondary" @click="$emit('retry')">تلاش دوباره</AdminButton>
        </slot>
      </div>
    </div>
  </div>
</template>
