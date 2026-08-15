<script setup lang="ts">
defineProps<{ label: string; hint?: string; error?: string; required?: boolean; forId?: string }>()
</script>

<template>
  <label class="block" :for="forId">
    <span class="mb-1.5 flex items-center gap-1 text-xs font-extrabold text-[var(--admin-text)]">{{ label }}<span v-if="required" class="text-[var(--admin-danger)]" aria-hidden="true">*</span></span>
    <slot />
    <span v-if="error" class="mt-1.5 block text-xs font-bold text-[var(--admin-danger)]" role="alert">{{ error }}</span>
    <span v-else-if="hint" class="mt-1.5 block text-[11px] leading-5 text-[var(--admin-muted)]">{{ hint }}</span>
  </label>
</template>
