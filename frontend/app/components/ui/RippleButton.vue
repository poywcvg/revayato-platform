<script setup lang="ts">
/**
 * Ripple button (uiverse.io), in the brand's green instead of the original
 * teal. Renders a NuxtLink when `to` is given. Letter-spacing and uppercase
 * from the original are dropped: they break Persian letter joining.
 */
defineProps<{ to?: string }>()
</script>

<template>
  <NuxtLink v-if="to" :to="to" class="ripple-btn">
    <i class="ripple-btn__wave" aria-hidden="true" />
    <span class="ripple-btn__label"><slot /></span>
    <i class="ripple-btn__wave" aria-hidden="true" />
  </NuxtLink>
  <button v-else type="button" class="ripple-btn">
    <i class="ripple-btn__wave" aria-hidden="true" />
    <span class="ripple-btn__label"><slot /></span>
    <i class="ripple-btn__wave" aria-hidden="true" />
  </button>
</template>

<style scoped>
.ripple-btn {
  --rb-bg: var(--theme-accent-primary);
  --rb-ink: var(--theme-on-accent);
  display: inline-flex;
  min-width: 200px;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  overflow: hidden;
  border: 0;
  border-radius: 0.75rem;
  background: var(--rb-bg);
  padding: 0.9rem 1.25rem;
  color: var(--rb-ink);
  font-size: 0.875rem;
  font-weight: 900;
  box-shadow: none;
  cursor: pointer;
  outline: 0;
}


.ripple-btn:hover { opacity: 0.95; }

.ripple-btn:focus-visible {
  outline: 2px solid var(--rb-bg);
  outline-offset: 3px;
}

.ripple-btn__label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.ripple-btn__wave {
  border-radius: 100%;
  animation: ripple-btn 0.6s linear infinite;
}

@keyframes ripple-btn {
  0% {
    box-shadow: 0 0 0 0 rgb(255 255 255 / 10%), 0 0 0 20px rgb(255 255 255 / 10%), 0 0 0 40px rgb(255 255 255 / 10%), 0 0 0 60px rgb(255 255 255 / 10%);
  }

  100% {
    box-shadow: 0 0 0 20px rgb(255 255 255 / 10%), 0 0 0 40px rgb(255 255 255 / 10%), 0 0 0 60px rgb(255 255 255 / 10%), 0 0 0 80px rgb(255 255 255 / 0%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ripple-btn__wave { animation: none; }
}
</style>
