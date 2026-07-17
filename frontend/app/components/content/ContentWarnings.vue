<script setup lang="ts">
defineProps<{ warnings: readonly string[]; compact?: boolean; dark?: boolean }>()
</script>

<template>
  <section v-if="warnings.length" class="rounded-2xl border border-warning/25 bg-warning/[.07] p-4" aria-labelledby="content-warnings-title">
    <div class="flex items-start gap-3">
      <span class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-warning/15 text-warning ring-1 ring-warning/25"><CinematicIcon name="alert-triangle" class="size-5" /></span>
      <div>
        <h2 id="content-warnings-title" class="text-sm font-black text-ink">هشدار محتوا</h2>
        <p v-if="!compact" class="mt-1 text-xs leading-5 text-secondary">پیش از تماشا، موارد زیر را در نظر بگیرید.</p>
        <ul class="mt-2 flex flex-wrap gap-2">
          <li v-for="warning in warnings" :key="warning" class="rounded-lg bg-elevated px-2.5 py-1 text-xs font-bold text-secondary ring-1 ring-line">{{ warning }}</li>
        </ul>
      </div>
    </div>
  </section>
</template>
