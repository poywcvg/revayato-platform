<script setup lang="ts">
import type { AppErrorDetails } from '~/types'

defineProps<{ error: AppErrorDetails }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <section class="rounded-lg border border-error/25 bg-error/15 px-3 py-2.5 text-error" role="alert" aria-live="polite">
    <div class="flex items-center justify-between gap-2">
      <div class="flex min-w-0 items-center">
        <svg class="size-5 shrink-0" width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M10 14.167q.354 0 .593-.24.24-.24.24-.594a.8.8 0 0 0-.24-.593.8.8 0 0 0-.594-.24.8.8 0 0 0-.593.24.8.8 0 0 0-.24.593q0 .354.24.594t.593.24m-.834-3.334h1.667v-5H9.166zm.833 7.5a8.1 8.1 0 0 1-3.25-.656 8.4 8.4 0 0 1-2.645-1.781 8.4 8.4 0 0 1-1.782-2.646A8.1 8.1 0 0 1 1.666 10q0-1.73.656-3.25a8.4 8.4 0 0 1 1.782-2.646 8.4 8.4 0 0 1 2.645-1.781A8.1 8.1 0 0 1 10 1.667q1.73 0 3.25.656a8.4 8.4 0 0 1 2.646 1.781 8.4 8.4 0 0 1 1.781 2.646 8.1 8.1 0 0 1 .657 3.25 8.1 8.1 0 0 1-.657 3.25 8.4 8.4 0 0 1-1.78 2.646 8.4 8.4 0 0 1-2.647 1.781 8.1 8.1 0 0 1-3.25.656" fill="currentColor" />
        </svg>
        <p class="ms-2 truncate text-sm font-bold">{{ error.title }}</p>
      </div>
      <button
        type="button"
        aria-label="بستن پیام خطا"
        class="grid size-8 shrink-0 cursor-pointer place-items-center rounded-md text-error/80 transition-all hover:bg-error/10 hover:text-error active:scale-90"
        @click="$emit('close')"
      >
        <CinematicIcon name="x" class="size-4" />
      </button>
    </div>
    <div v-if="error.message || error.fields.length || error.reason || error.hint" class="mt-1 space-y-1 pe-10 text-xs leading-6 text-error/85">
      <p v-if="error.message && error.message !== error.title">{{ error.message }}</p>
      <ul v-if="error.fields.length">
        <li v-for="item in error.fields" :key="item.field"><strong>{{ item.label }}:</strong> {{ item.message }}</li>
      </ul>
      <p v-else-if="error.reason && error.reason !== error.message">
        <strong>دلیل:</strong> {{ error.reason }}
      </p>
      <p v-if="error.hint" class="text-error/70">{{ error.hint }}</p>
    </div>
  </section>
</template>
