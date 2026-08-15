/**
 * Shared polling composable for the admin panel.
 *
 * Replaces the hand-rolled `setInterval` loops scattered across
 * catalog-sync (2.5s), provider-import (2.5s) and the dashboards (45/60s).
 * Timers are always cleared on unmount; polling can be stopped on a predicate.
 */
export interface UsePollingOptions {
  /** Delay between ticks in milliseconds. */
  intervalMs?: number
  /** Whether polling should start immediately on call. */
  immediate?: boolean
  /** Max ticks before auto-stop. 0 = unlimited. */
  maxTicks?: number
  /** Stop early when the predicate returns true (checked after each tick). */
  stopWhen?: () => boolean
}

export function usePolling(callback: () => void | Promise<void>, options: UsePollingOptions = {}) {
  const { intervalMs = 3000, immediate = true, maxTicks = 0, stopWhen } = options

  const isActive = ref(false)
  let timer: ReturnType<typeof setInterval> | undefined
  let ticks = 0

  function clear() {
    if (timer) {
      clearInterval(timer)
      timer = undefined
    }
  }

  async function tickOnce() {
    if (!isActive.value) return
    ticks += 1
    try {
      await callback()
    } catch {
      // Polling callbacks should be resilient; errors are visual/state-driven at the call site.
    }
    if (!isActive.value) return
    if ((maxTicks > 0 && ticks >= maxTicks) || (stopWhen && stopWhen())) {
      stop()
    }
  }

  function start() {
    if (isActive.value || import.meta.server) return
    isActive.value = true
    ticks = 0
    void tickOnce()
    timer = setInterval(() => void tickOnce(), intervalMs)
  }

  function stop() {
    isActive.value = false
    clear()
  }

  if (immediate) start()

  onBeforeUnmount(() => stop())

  return { start, stop, isActive }
}