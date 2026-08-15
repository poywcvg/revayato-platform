import type { MaybeRefOrGetter } from 'vue'

export function useHeroSlider(itemCount: MaybeRefOrGetter<number>, intervalMs = 6000) {
  const currentIndex = ref(0)
  const isPaused = ref(false)
  const reducedMotionPreference = usePreferredReducedMotion()
  const documentVisibility = useDocumentVisibility()
  const pauseReasons = new Set<string>()
  let timer: number | undefined
  let mounted = false

  const count = computed(() => Math.max(0, toValue(itemCount)))
  const reducedMotion = computed(() => reducedMotionPreference.value === 'reduce')

  function clearTimer() {
    if (timer !== undefined) window.clearTimeout(timer)
    timer = undefined
  }

  function schedule() {
    clearTimer()
    isPaused.value = pauseReasons.size > 0 || reducedMotion.value
    if (!mounted || isPaused.value || count.value < 2) return
    timer = window.setTimeout(() => {
      currentIndex.value = (currentIndex.value + 1) % count.value
    }, Math.max(4000, intervalMs))
  }

  function pause(reason = 'interaction') {
    pauseReasons.add(reason)
    schedule()
  }

  function resume(reason = 'interaction') {
    pauseReasons.delete(reason)
    schedule()
  }

  function goTo(index: number) {
    if (!count.value) return
    currentIndex.value = (index + count.value) % count.value
    schedule()
  }

  function next() {
    goTo(currentIndex.value + 1)
  }

  function previous() {
    goTo(currentIndex.value - 1)
  }

  watch(count, (value) => {
    if (!value) currentIndex.value = 0
    else if (currentIndex.value >= value) currentIndex.value = value - 1
    schedule()
  })
  watch(currentIndex, schedule)
  watch(reducedMotion, (reduce) => {
    if (reduce) pauseReasons.add('reduced-motion')
    else pauseReasons.delete('reduced-motion')
    schedule()
  }, { immediate: true })
  watch(documentVisibility, (visibility) => {
    if (visibility === 'visible') pauseReasons.delete('document-hidden')
    else pauseReasons.add('document-hidden')
    schedule()
  }, { immediate: true })

  onMounted(() => {
    mounted = true
    schedule()
  })

  onBeforeUnmount(() => {
    mounted = false
    clearTimer()
  })

  return {
    currentIndex: readonly(currentIndex),
    isPaused: readonly(isPaused),
    reducedMotion,
    goTo,
    next,
    previous,
    pause,
    resume,
  }
}
