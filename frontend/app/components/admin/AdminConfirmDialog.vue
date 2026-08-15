<script setup lang="ts">
defineProps<{ open: boolean; title: string; message: string; confirmLabel?: string; dangerous?: boolean; loading?: boolean }>()
defineEmits<{ close: []; confirm: [] }>()
</script>

<template>
  <AdminModal :open="open" :title="title" size="sm" :closeable="!loading" @close="$emit('close')">
    <div class="px-6 py-5"><p class="text-sm leading-7 text-[var(--admin-muted)]">{{ message }}</p><slot /></div>
    <template #footer><div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><AdminButton variant="ghost" :disabled="loading" @click="$emit('close')">انصراف</AdminButton><AdminButton :variant="dangerous ? 'danger' : 'primary'" :loading="loading" @click="$emit('confirm')">{{ confirmLabel || 'تأیید' }}</AdminButton></div></template>
  </AdminModal>
</template>
