import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { FactoryData } from '@/types'
import { apiUrl, wsUrl } from '@/config'

export type ConnState = 'idle' | 'connecting' | 'online' | 'error'

const RETRY_BASE_MS = 1000
const RETRY_MAX_MS = 15000

export const useFactoryStore = defineStore('factory', () => {
  const data = ref<FactoryData | null>(null)
  const connected = ref(false)
  const connState = ref<ConnState>('idle')
  const errorMsg = ref('')
  let ws: WebSocket | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let retryCount = 0
  let closedByUser = false

  function setError(msg: string) {
    connState.value = 'error'
    connected.value = false
    errorMsg.value = msg
  }

  // 先通过 REST 确认后端可达、口径可获取；失败给出明确提示（WS 上无法区分 404/拒绝）
  async function probeBackend(): Promise<void> {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 5000)
    try {
      const res = await fetch(apiUrl('/api/config'), { signal: ctrl.signal })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch (e: any) {
      throw new Error(
        `无法从后端获取统计口径/健康检查接口（${apiUrl('/api/config')}）：` +
        `${e?.name === 'AbortError' ? '请求超时（5s）' : e?.message || e}。` +
        '请确认后端已按同一 .env 启动（端口/BACKEND_HOST），然后点击重试。'
      )
    } finally {
      clearTimeout(timer)
    }
  }

  function scheduleRetry() {
    if (closedByUser || retryTimer) return
    const delay = Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** retryCount)
    retryCount += 1
    retryTimer = setTimeout(() => {
      retryTimer = null
      connect()
    }, delay)
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    closedByUser = false
    errorMsg.value = ''
    connState.value = 'connecting'

    probeBackend()
      .then(() => openSocket())
      .catch((e) => {
        setError(e.message)
        scheduleRetry()
      })
  }

  function openSocket() {
    const s = new WebSocket(wsUrl('/ws'))
    s.onopen = () => {
      connected.value = true
      connState.value = 'online'
      errorMsg.value = ''
      retryCount = 0
    }
    s.onmessage = (e) => {
      try {
        data.value = JSON.parse(e.data)
      } catch (err) {
        setError('后端推送的数据无法解析，可能版本/配置不一致，请刷新或重试。')
      }
    }
    s.onerror = () => {
      // onclose 会紧随其后，统一在 onclose 处理提示与重试
    }
    s.onclose = () => {
      connected.value = false
      ws = null
      if (closedByUser) {
        connState.value = 'idle'
        return
      }
      setError('与后端的实时连接已断开，正在自动重试；也可立即手动重试。')
      scheduleRetry()
    }
    ws = s
  }

  // 手动重试入口（界面按钮调用）
  function retry() {
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    retryCount = 0
    ws?.close()
    ws = null
    connect()
  }

  function disconnect() {
    closedByUser = true
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    ws?.close()
    ws = null
    connected.value = false
    connState.value = 'idle'
  }

  return { data, connected, connState, errorMsg, connect, retry, disconnect }
})
