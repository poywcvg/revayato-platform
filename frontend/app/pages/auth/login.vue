<script setup lang="ts">
definePageMeta({ layout: 'auth', middleware: 'guest' })
useSeoMeta({ title: 'ورود' })
</script>

<template>
  <AuthPortal initial-mode="login" />
</template>
