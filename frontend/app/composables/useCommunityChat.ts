export interface CommunityChatMessage {
  id: number
  username: string
  display_name: string
  body: string
  created_at: string
}

const OPEN_POLL_MS = 12_000
const IDLE_POLL_MS = 60_000
const SEEN_KEY = 'revayato:community-seen-id'
const INVITE_KEY = 'revayato:community-invite-day'

function readSeenId() {
  try {
    return Number(localStorage.getItem(SEEN_KEY) || 0) || 0
  } catch {
    return 0
  }
}

export function useCommunityChat() {
  const { api } = useApi()
  const authStore = useAuthStore()

  const isOpen = useState<boolean>('community-chat-open', () => false)
  const messages = useState<CommunityChatMessage[]>('community-chat-messages', () => [])
  const pending = useState<boolean>('community-chat-pending', () => false)
  const sending = useState<boolean>('community-chat-sending', () => false)
  const error = useState<string>('community-chat-error', () => '')
  const unread = useState<number>('community-chat-unread', () => 0)
  const inviteVisible = useState<boolean>('community-chat-invite', () => false)

  let pollTimer: ReturnType<typeof setInterval> | undefined
  let inviteTimer: ReturnType<typeof setTimeout> | undefined
  let lastFetchAt = 0

  function markSeen() {
    const lastId = messages.value.at(-1)?.id || 0
    unread.value = 0
    try {
      localStorage.setItem(SEEN_KEY, String(lastId))
    } catch { /* private mode */ }
  }

  function refreshUnread() {
    if (isOpen.value) {
      markSeen()
      return
    }
    const seen = readSeenId()
    const fresh = messages.value.filter(m => m.id > seen).length
    unread.value = Math.min(fresh, 9)
  }

  async function fetchMessages(silent = true) {
    if (!import.meta.client) return
    if (!silent) pending.value = true
    error.value = ''
    try {
      const res = await api<{ messages?: CommunityChatMessage[] }>('/community/messages/')
      messages.value = [...(res?.messages || [])].sort((a, b) => a.id - b.id).slice(-30)
      lastFetchAt = Date.now()
      refreshUnread()
    } catch {
      if (!silent) error.value = 'دریافت گفتگو ممکن نشد. دوباره تلاش کن.'
    } finally {
      if (!silent) pending.value = false
    }
  }

  async function send(body: string) {
    const text = body.trim().slice(0, 500)
    if (!text || sending.value) return false
    if (!authStore.isAuthenticated) return false
    sending.value = true
    error.value = ''
    try {
      const created = await api<CommunityChatMessage>('/community/messages/', {
        method: 'POST',
        body: { body: text },
      })
      if (created?.id) {
        if (!messages.value.some(m => m.id === created.id)) {
          messages.value = [...messages.value, created].slice(-30)
        }
        markSeen()
      } else {
        await fetchMessages(true)
      }
      return true
    } catch {
      error.value = 'ارسال نشد. وصل هستی؟ دوباره بفرست.'
      return false
    } finally {
      sending.value = false
    }
  }

  function open() {
    isOpen.value = true
    inviteVisible.value = false
    markSeen()
    void fetchMessages(true)
  }

  function close() {
    isOpen.value = false
  }

  function toggle() {
    if (isOpen.value) close()
    else open()
  }

  function startPolling() {
    stopPolling()
    if (!import.meta.client) return
    // Open lounge stays live; a closed lounge only refreshes its badge about
    // once a minute so background tabs stop taxing a busy backend.
    pollTimer = setInterval(() => {
      if (document.hidden) return
      if (isOpen.value) {
        void fetchMessages(true)
        return
      }
      if (Date.now() - lastFetchAt >= IDLE_POLL_MS) void fetchMessages(true)
    }, OPEN_POLL_MS)
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = undefined
  }

  function scheduleInvite() {
    if (!import.meta.client) return
    clearTimeout(inviteTimer)
    let today = ''
    try {
      today = new Date().toISOString().slice(0, 10)
      if (localStorage.getItem(INVITE_KEY) === today) return
    } catch { /* ignore */ }
    inviteTimer = setTimeout(() => {
      if (!isOpen.value) {
        inviteVisible.value = true
        try {
          localStorage.setItem(INVITE_KEY, today)
        } catch { /* ignore */ }
        setTimeout(() => { inviteVisible.value = false }, 9000)
      }
    }, 7000)
  }

  function dismissInvite() {
    inviteVisible.value = false
    if (inviteTimer) clearTimeout(inviteTimer)
  }

  // Shared singleton: polling starts once per tab. The first fetch waits for
  // idle so the lounge never competes with the page's own critical requests.
  if (import.meta.client && !(globalThis as { __communityChatPolling?: boolean }).__communityChatPolling) {
    (globalThis as { __communityChatPolling?: boolean }).__communityChatPolling = true
    startPolling()
    scheduleInvite()
    const firstFetch = () => void fetchMessages(true)
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(firstFetch, { timeout: 4000 })
    } else {
      setTimeout(firstFetch, 2000)
    }
  }

  watch(isOpen, (open) => {
    if (open) markSeen()
  })

  return {
    isOpen,
    messages: readonly(messages),
    pending: readonly(pending),
    sending: readonly(sending),
    error: readonly(error),
    unread: readonly(unread),
    inviteVisible: readonly(inviteVisible),
    open,
    close,
    toggle,
    send,
    refresh: () => fetchMessages(false),
    dismissInvite,
  }
}
