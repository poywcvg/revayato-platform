import type {
  WatchPartyConnectionStatus,
  WatchPartyMember,
  WatchPartyMessage,
  WatchPartyPlaybackEvent,
  WatchPartyPlaybackEventType,
  WatchPartyPlaybackState,
  WatchPartySocketError,
  WatchRoom,
} from '~/types'
import { accessTokenNeedsRefresh } from '~/utils/jwtSession'

interface SocketPayload {
  type: string
  room?: Partial<WatchRoom>
  members?: WatchPartyMember[]
  messages?: WatchPartyMessage[]
  member?: WatchPartyMember
  user_id?: number
  message?: WatchPartyMessage | string
  playback_state?: WatchPartyPlaybackState
  code?: string
  client_time_ms?: number
  server_time_ms?: number
}

const PLAYBACK_EVENTS = new Set<WatchPartyPlaybackEventType>([
  'playback.state',
  'playback.play',
  'playback.pause',
  'playback.seek',
  'playback.sync',
  'playback.sync.response',
])

export function useWatchPartySocket(inviteCode: MaybeRef<string>) {
  const config = useRuntimeConfig()
  const { refreshAccessToken } = useApi()
  // Shared composable so this ref carries the same persistence options as every
  // other reader; a bare useCookie() here would re-stamp it without them.
  const { accessToken } = useAuthCookies()
  const room = shallowRef<WatchRoom | null>(null)
  const members = ref<WatchPartyMember[]>([])
  const messages = ref<WatchPartyMessage[]>([])
  const playbackState = ref<WatchPartyPlaybackState | null>(null)
  const connectionStatus = ref<WatchPartyConnectionStatus>('idle')
  const socketError = ref<WatchPartySocketError | null>(null)
  const lastPlaybackEvent = shallowRef<WatchPartyPlaybackEvent | null>(null)
  const lastChatMessage = shallowRef<WatchPartyMessage | null>(null)
  const syncRequestSequence = ref(0)

  let socket: WebSocket | null = null
  let manualDisconnect = false
  let reconnectAttempts = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined
  let heartbeatTimer: ReturnType<typeof setInterval> | undefined
  let latencyTimer: ReturnType<typeof setInterval> | undefined
  let authRecoveryRequest: Promise<void> | null = null
  let sequence = 0
  let lastPlaybackStampMs = 0
  let wasConnected = false

  function websocketUrl() {
    let base = String(config.public.wsBase).replace(/\/$/, '')
    if (!base) {
      const apiBase = String(config.public.apiBase).replace(/\/$/, '')
      if (/^https?:\/\//.test(apiBase)) {
        base = apiBase.replace(/^http/, 'ws').replace(/\/api$/, '')
      } else if (import.meta.client) {
        base = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
      }
    }
    return `${base}/ws/watch-party/${encodeURIComponent(toValue(inviteCode))}/`
  }

  function sendEvent(payload: Record<string, unknown>) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify(payload))
    return true
  }

  function upsertMember(member: WatchPartyMember) {
    const index = members.value.findIndex(item => item.user.id === member.user.id)
    if (index >= 0) members.value[index] = member
    else members.value.push(member)
    members.value = [...members.value].sort((a, b) => {
      if (a.role !== b.role) return a.role === 'host' ? -1 : 1
      return a.joined_at.localeCompare(b.joined_at)
    })
  }

  function applyPayload(payload: SocketPayload) {
    if (payload.type === 'room.state') {
      room.value = room.value
        ? { ...room.value, ...payload.room }
        : payload.room as WatchRoom
      if (payload.members) members.value = payload.members
      if (payload.messages) messages.value = payload.messages
    } else if (payload.type === 'member.joined' && payload.member) {
      upsertMember(payload.member)
    } else if (payload.type === 'member.left') {
      if (payload.member) upsertMember({ ...payload.member, is_online: false })
      else if (payload.user_id) {
        members.value = members.value.map(member => member.user.id === payload.user_id
          ? { ...member, is_online: false }
          : member)
      }
    } else if (payload.type === 'chat.message' && payload.message && typeof payload.message !== 'string') {
      if (!messages.value.some(message => message.id === (payload.message as WatchPartyMessage).id)) {
        const incomingMessage = payload.message as WatchPartyMessage
        messages.value.push(incomingMessage)
        lastChatMessage.value = incomingMessage
      }
    } else if (payload.type === 'error') {
      socketError.value = {
        code: payload.code || 'socket_error',
        message: typeof payload.message === 'string' ? payload.message : 'خطای ارتباط زنده رخ داد.',
      }
    } else if (payload.type === 'latency.pong') {
      updateLatency(payload)
    } else if (payload.type === 'playback.sync.requested') {
      syncRequestSequence.value += 1
    }

    if (PLAYBACK_EVENTS.has(payload.type as WatchPartyPlaybackEventType) && payload.playback_state) {
      const stamp = Number(payload.playback_state.server_time_ms)
        || Date.parse(payload.playback_state.updated_at)
        || 0
      if (stamp && lastPlaybackStampMs && stamp + 350 < lastPlaybackStampMs) {
        return
      }
      if (stamp) lastPlaybackStampMs = Math.max(lastPlaybackStampMs, stamp)
      refineClockFromEvent(payload.playback_state)
      playbackState.value = payload.playback_state
      lastPlaybackEvent.value = {
        sequence: ++sequence,
        type: payload.type as WatchPartyPlaybackEventType,
        state: payload.playback_state,
      }
    } else if (payload.type === 'room.state' && payload.playback_state) {
      const stamp = Number(payload.playback_state.server_time_ms)
        || Date.parse(payload.playback_state.updated_at)
        || 0
      if (stamp) lastPlaybackStampMs = Math.max(lastPlaybackStampMs, stamp)
      playbackState.value = payload.playback_state
      lastPlaybackEvent.value = {
        sequence: ++sequence,
        type: 'playback.state',
        state: payload.playback_state,
      }
    }
  }

  const latencyMs = ref<number | null>(null)
  const clockOffsetMs = ref(0)

  function updateLatency(payload: SocketPayload) {
    const clientTime = Number(payload.client_time_ms)
    const serverTime = Number(payload.server_time_ms)
    if (!Number.isFinite(clientTime) || !Number.isFinite(serverTime)) return
    const receivedAt = Date.now()
    const roundTrip = Math.max(0, receivedAt - clientTime)
    const sampleOffset = serverTime - (clientTime + roundTrip / 2)
    latencyMs.value = latencyMs.value === null
      ? Math.round(roundTrip)
      : Math.round(latencyMs.value * 0.7 + roundTrip * 0.3)
    clockOffsetMs.value = clockOffsetMs.value * 0.75 + sampleOffset * 0.25
  }

  function refineClockFromEvent(state: { server_time_ms?: number, updated_at: string }) {
    const stamp = Number(state.server_time_ms) || Date.parse(state.updated_at)
    if (!Number.isFinite(stamp) || !stamp) return
    const latency = latencyMs.value
    const sampleOffset = stamp - (Date.now() - (latency ?? 0) / 2)
    clockOffsetMs.value = clockOffsetMs.value * 0.8 + sampleOffset * 0.2
  }

  function serverNowMs() {
    return Date.now() + clockOffsetMs.value
  }

  function sendLatencyPing() {
    sendEvent({ type: 'latency.ping', client_time_ms: Date.now() })
  }

  function scheduleReconnect() {
    if (manualDisconnect || room.value?.status !== 'active') return
    connectionStatus.value = 'reconnecting'
    const delay = Math.min(750 * 2 ** reconnectAttempts, 10000) * (0.8 + Math.random() * 0.4)
    reconnectAttempts += 1
    reconnectTimer = setTimeout(connect, delay)
  }

  async function recoverAfterAuthExpiry() {
    if (manualDisconnect || authRecoveryRequest) return
    connectionStatus.value = 'reconnecting'
    authRecoveryRequest = refreshAccessToken()
      .then((token) => {
        if (!token || manualDisconnect) {
          connectionStatus.value = 'error'
          socketError.value = { code: 'session_expired', message: 'نشست شما منقضی شده است؛ دوباره وارد شوید.' }
          return
        }
        reconnectAttempts = 0
        connect()
      })
      .catch(() => {
        connectionStatus.value = 'error'
        socketError.value = { code: 'session_refresh_failed', message: 'تمدید نشست ممکن نشد؛ دوباره تلاش کنید.' }
      })
      .finally(() => {
        authRecoveryRequest = null
      })
    await authRecoveryRequest
  }

  function connect() {
    if (
      !import.meta.client
      || !accessToken.value
      || socket?.readyState === WebSocket.CONNECTING
      || socket?.readyState === WebSocket.OPEN
    ) return
    // The handshake is refused outright for an expired token, which would burn a
    // reconnect attempt. Rotate first and let the recovery path reconnect.
    if (accessTokenNeedsRefresh(accessToken.value)) {
      void recoverAfterAuthExpiry()
      return
    }
    manualDisconnect = false
    socketError.value = null
    connectionStatus.value = reconnectAttempts ? 'reconnecting' : 'connecting'
    const protocol = `watchparty.jwt.${accessToken.value}`
    socket = new WebSocket(websocketUrl(), [protocol])
    socket.addEventListener('open', () => {
      const reconnected = wasConnected
      connectionStatus.value = 'connected'
      wasConnected = true
      reconnectAttempts = 0
      lastPlaybackStampMs = 0
      sendEvent({ type: 'room.join' })
      sendLatencyPing()
      if (reconnected) sendEvent({ type: 'playback.sync.request' })
      heartbeatTimer = setInterval(() => sendEvent({ type: 'heartbeat' }), 15000)
      latencyTimer = setInterval(sendLatencyPing, 3000)
    })
    socket.addEventListener('message', (event) => {
      try {
        applyPayload(JSON.parse(String(event.data)) as SocketPayload)
      } catch {
        socketError.value = { code: 'invalid_payload', message: 'پاسخ زنده نامعتبر دریافت شد.' }
      }
    })
    socket.addEventListener('error', () => {
      connectionStatus.value = 'error'
      socketError.value = { code: 'connection_error', message: 'ارتباط زنده با اتاق برقرار نشد.' }
    })
    socket.addEventListener('close', (event) => {
      if (heartbeatTimer) clearInterval(heartbeatTimer)
      heartbeatTimer = undefined
      if (latencyTimer) clearInterval(latencyTimer)
      latencyTimer = undefined
      socket = null
      if (event.code === 4000 || event.code === 4409) {
        room.value = room.value ? { ...room.value, status: 'ended' } : room.value
        connectionStatus.value = 'disconnected'
        return
      }
      if (event.code === 4401 || event.code === 4403 || event.code === 4404) {
        if (event.code === 4401) {
          void recoverAfterAuthExpiry()
          return
        }
        connectionStatus.value = 'error'
        socketError.value = {
          code: `socket_${event.code}`,
          message: event.code === 4404 ? 'اتاق پیدا نشد.' : 'اجازه ورود به ارتباط زنده را ندارید.',
        }
        return
      }
      connectionStatus.value = 'disconnected'
      scheduleReconnect()
    })
  }

  function disconnect(sendLeave = true) {
    manualDisconnect = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (heartbeatTimer) clearInterval(heartbeatTimer)
    if (latencyTimer) clearInterval(latencyTimer)
    reconnectTimer = undefined
    heartbeatTimer = undefined
    latencyTimer = undefined
    if (sendLeave) sendEvent({ type: 'room.leave' })
    socket?.close(1000)
    socket = null
    connectionStatus.value = 'disconnected'
  }

  function setInitialRoom(value: WatchRoom) {
    room.value = value
    if (value.playback_state) {
      playbackState.value = value.playback_state
      const stamp = Number(value.playback_state.server_time_ms)
        || Date.parse(value.playback_state.updated_at)
        || 0
      if (stamp) lastPlaybackStampMs = Math.max(lastPlaybackStampMs, stamp)
    }
  }

  onBeforeUnmount(() => disconnect())

  return {
    room: readonly(room),
    members: readonly(members),
    messages: readonly(messages),
    playbackState: readonly(playbackState),
    connectionStatus: readonly(connectionStatus),
    latencyMs: readonly(latencyMs),
    socketError: readonly(socketError),
    lastPlaybackEvent: readonly(lastPlaybackEvent),
    lastChatMessage: readonly(lastChatMessage),
    syncRequestSequence: readonly(syncRequestSequence),
    connect,
    disconnect,
    sendEvent,
    setInitialRoom,
    requestSync: () => sendEvent({ type: 'playback.sync.request' }),
    serverNowMs,
    sendChat: (message: string) => sendEvent({ type: 'chat.message', message }),
  }
}
