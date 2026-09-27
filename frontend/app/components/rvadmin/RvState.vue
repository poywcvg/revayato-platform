<script setup lang="ts">
import Inbox from '~icons/lucide/inbox'
import AlertTriangle from '~icons/lucide/triangle-alert'

withDefaults(defineProps<{
  kind?: 'empty' | 'error'
  title: string
  message?: string
}>(), { kind: 'empty', message: '' })

defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center px-6 py-12 text-center">
    <span
      class="grid size-14 place-items-center rounded-2xl"
      :style="kind === 'error'
        ? { color: 'var(--rv-danger)', background: 'var(--rv-danger-soft)' }
        : { color: 'var(--rv-muted)', background: 'var(--rv-surface-3)' }"
    >
      <AlertTriangle v-if="kind === 'error'" class="size-6" />
      <Inbox v-else class="size-6" />
    </span>
    <h3 class="mt-4 text-sm font-black text-[var(--rv-text)]">{{ title }}</h3>
    <p v-if="message" class="mt-1.5 max-w-sm text-xs leading-6 text-[var(--rv-muted)]">{{ message }}</p>
    <button v-if="kind === 'error'" type="button" class="rv-btn rv-btn--ghost rv-focus mt-4" @click="$emit('retry')">
      تلاش دوباره
    </button>
  </div>
</template>
