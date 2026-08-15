<script setup lang="ts">
defineProps<{
  error: string | null
  pending?: boolean
}>()

defineEmits<{
  retry: []
}>()
</script>

<template>
  <aside
    v-if="error"
    class="flex flex-col gap-3 rounded-2xl border border-warning/30 bg-warning/10 p-4 text-ink sm:flex-row sm:items-center sm:justify-between"
    role="status"
    aria-live="polite"
  >
    <div class="flex items-start gap-3">
      <span
        class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-warning/15 text-warning ring-1 ring-warning/25"
      >
        <CinematicIcon name="signal-off" class="size-5" />
      </span>
      <div>
        <p class="text-sm font-black">فهرست محتوا در دسترس نیست</p>
        <p class="mt-1 text-xs leading-6 text-secondary">
          ارتباط با سرویس محتوا برقرار نشد. اتصال اینترنت را بررسی کن و دوباره تلاش کن.
        </p>
      </div>
    </div>
    <div class="flex shrink-0 items-center gap-2">
      <button
        type="button"
        class="inline-flex min-h-11 items-center gap-2 rounded-xl bg-warning px-3.5 py-2 text-xs font-black text-[#271805] transition hover:brightness-110 disabled:cursor-wait disabled:opacity-60"
        :disabled="pending"
        @click="$emit('retry')"
      >
        <CinematicIcon
          name="refresh"
          class="size-4"
          :class="pending && 'animate-spin'"
        />
        {{ pending ? 'در حال اتصال' : 'تلاش دوباره' }}
      </button>
    </div>
  </aside>
</template>
