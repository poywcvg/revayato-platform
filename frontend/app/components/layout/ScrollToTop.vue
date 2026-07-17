<script setup lang="ts">
const visible = ref(false)
let observer: IntersectionObserver | null = null

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(() => {
  const sentinel = document.getElementById('page-top-sentinel')
  if (!sentinel || !('IntersectionObserver' in window)) return
  observer = new IntersectionObserver(([entry]) => {
    visible.value = !entry?.isIntersecting
  }, { rootMargin: '80px 0px 0px' })
  observer.observe(sentinel)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <Transition name="scroll-top">
    <button v-if="visible" type="button" class="scroll-top-button" aria-label="بازگشت به ابتدای صفحه" @click="scrollToTop">
      <CinematicIcon name="arrow-up" class="size-4.5" />
      <span class="hidden text-[10px] font-black sm:inline">بالای صفحه</span>
    </button>
  </Transition>
</template>
