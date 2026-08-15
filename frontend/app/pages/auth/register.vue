<script setup lang="ts">
definePageMeta({ layout: 'auth', middleware: 'guest' })
useSeoMeta({ title: 'ساخت حساب' })
</script>

<template>
  <AuthPortal initial-mode="register" />
</template>
