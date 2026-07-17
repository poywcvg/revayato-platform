<script setup lang="ts">
import { Toaster } from 'vue-sonner'
</script>

<template>
  <ClientOnly>
    <Toaster theme="dark" position="top-center" dir="rtl" close-button :rich-colors="false" :visible-toasts="4" :duration="4500" :gap="10" container-aria-label="اعلان‌های سایت" class="cinema-toaster">
      <template #success-icon><CinematicIcon name="check-circle" class="size-5 text-success" /></template>
      <template #error-icon><CinematicIcon name="alert-triangle" class="size-5 text-error" /></template>
      <template #warning-icon><CinematicIcon name="alert-triangle" class="size-5 text-warning" /></template>
      <template #info-icon><CinematicIcon name="info" class="size-5 text-info" /></template>
    </Toaster>
  </ClientOnly>
</template>
