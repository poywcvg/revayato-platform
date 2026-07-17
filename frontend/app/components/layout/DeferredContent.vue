<script setup lang="ts">
const props = withDefaults(defineProps<{
  minHeight?: string
  rootMargin?: string
}>(), {
  minHeight: '32rem',
  rootMargin: '360px 0px',
})

const root = useTemplateRef<HTMLElement>('root')
const visible = ref(false)
let observer: IntersectionObserver | null = null

onMounted(() => {
  if (!('IntersectionObserver' in window)) {
    visible.value = true
    return
  }

  observer = new IntersectionObserver(([entry]) => {
    if (!entry?.isIntersecting) return
    visible.value = true
    observer?.disconnect()
    observer = null
  }, { rootMargin: props.rootMargin })

  if (root.value) observer.observe(root.value)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="root" :style="visible ? undefined : { minHeight }" :aria-busy="!visible">
    <slot v-if="visible" />
    <div v-else class="content-section" aria-hidden="true">
      <div class="rounded-3xl border border-white/[.06] bg-white/[.018] p-5">
        <div class="h-3 w-24 rounded-full bg-white/[.06]" />
        <div class="mt-3 h-6 w-52 max-w-[70%] rounded-lg bg-white/[.07]" />
        <div class="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <div v-for="index in 6" :key="index" class="aspect-[2/3] rounded-2xl bg-white/[.035] ring-1 ring-white/[.045]" />
        </div>
      </div>
    </div>
  </div>
</template>
