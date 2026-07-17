<script setup lang="ts">
const props = withDefaults(
  defineProps<{ objectId: number; dark?: boolean }>(),
  { dark: false },
);
const { isLiked, toggleLike } = useLibrary();
const notifications = useNotifications();
const liked = computed(() => isLiked(props.objectId));

function handleLike() {
  const adding = !liked.value;
  toggleLike(props.objectId);
  if (adding) notifications.success('پسندیده شد', 'از این انتخاب برای بهتر شدن پیشنهادها استفاده می‌کنیم.');
  else notifications.info('پسند برداشته شد', 'این تغییر در پیشنهادهای بعدی در نظر گرفته می‌شود.');
}
</script>

<template>
  <div class="flex flex-wrap gap-2">
    <button
      type="button"
      class="inline-flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-black transition"
      :class="
        liked
          ? 'bg-error text-ink'
          : dark
            ? 'bg-white/10 text-ink ring-1 ring-white/20 hover:bg-white/20'
            : 'bg-elevated text-secondary ring-1 ring-line hover:text-error hover:ring-error/40'
      "
      :aria-pressed="liked"
      @click="handleLike"
    >
      <CinematicIcon
        name="heart"
        class="size-5"
        :filled="liked"
        :stroke-width="liked ? 2.25 : 1.8"
      />{{ liked ? "پسندیده شد" : "پسندیدن" }}
    </button>
    <WatchlistButton :id="objectId" :dark="dark" />
  </div>
</template>
