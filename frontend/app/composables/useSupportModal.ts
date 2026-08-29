/** Global quick-support modal state so any entry point can summon it. */
export function useSupportModal() {
  const isOpen = useState('support-modal-open', () => false)
  const presetCategory = useState<string>('support-modal-preset', () => '')

  function open(category = '') {
    presetCategory.value = String(category || '')
    isOpen.value = true
  }

  function close() {
    isOpen.value = false
  }

  return { isOpen, presetCategory, open, close }
}
