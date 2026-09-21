import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { FactoryData } from '@/types'
import { loadBuildStatConfig, httpUrl, wsUrl, type StatConfig } from '@/config'

type ConnState = 'idle' | 'connecting' | 'live' | 'polling' | 'error'

const MAX_BACKOFF_MS = 10000
const POLL_INTERVAL_MS = 2000
const FETCH_TIMEOUT_MS = 5000

export const useFactoryStore = defineStore('factory', () => {
  const data = ref<FactoryData | null>(null)
  const connected = ref(false)          // 实时链路（WS）是否在线
  const connState = ref<ConnState>('idle')
  const lastError = ref('')             // 取数失败原因，界面据此提示
  const retrying = ref(false)           // 是否处于自动重试中
  const configError = ref('')           // 构建期口径配置非法时的提示
  const configFetchError = ref('')      // 运行时 /api/config 取不到数据的提示

  const { config: buildConfig, errors } = loadBuildStatConfig()
  if (errors.length) configError.value = `统计口径配置无效（已回退默认值）：${errors.join('；')}`
  const statConfig = ref<StatConfig>(buildConfig)

  let ws: WebSocket | null = null
  let manualClose = false
  let suppressCloseHandler = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let attempts = 0
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let disposed = false

  function setError(msg: string) {
    lastError.value = msg
  }

  async function fetchConfig(): Promise<void> {
    const resp = await fetchWithTimeout(httpUrl('/api/config'))
    const body = await resp.json()
    const c = body?.config
    if (typeof c?.shift_start_hour !== 'number' ||
        typeof c?.sample_interval_sec !== 'number' ||
        typeof c?.retention_sec !== 'number') {
      throw new Error('后端 /api/config 返回的统计口径字段缺失')
    }
    statConfig.value = {
      shiftStartHour: c.shift_start_hour,
      sampleIntervalSec: c.sample_interval_sec,
      retentionSec: c.retention_sec,
      source: 'backend'
    }
    configFetchError.value = ''
  }

  async function fetchSnapshot(): Promise<FactoryData> {
    const [d, o] = await Promise.all([
      fetchWithTimeout(httpUrl('/api/devices')).then(r => r.json()),
      fetchWithTimeout(httpUrl('/api/oee')).then(r => r.json())
    ])
    if (!Array.isArray(d?.devices) || !Array.isArray(o?.oee)) {
      throw new Error('接口返回的数据结构异常')
    }
    return {
      devices: d.devices,
      production: typeof d.shift_production === 'number'
        ? d.shift_production
        : d.devices.reduce((s: number, x: { production_count: number }) => s + x.production_count, 0),
      anomalies: d.anomalies ?? [],
      oee: o.oee,
      shift: d.shift ?? { start_hour: statConfig.value.shiftStartHour, start_ts: 0 }
    }
  }

  function fetchWithTimeout(url: string): Promise<Response> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`请求超时(${FETCH_TIMEOUT_MS / 1000}s): ${url}`)), FETCH_TIMEOUT_MS)
      fetch(url).then(resp => {
        clearTimeout(timer)
        if (!resp.ok) reject(new Error(`接口不可用: ${url} HTTP ${resp.status}`))
        else resolve(resp)
      }).catch(err => { clearTimeout(timer); reject(err) })
    })
  }

  function applyPayload(payload: any) {
    if (!payload || !Array.isArray(payload.devices) || !Array.isArray(payload.oee)) {
      throw new Error('WS 数据结构异常')
    }
    data.value = payload as FactoryData
    lastError.value = ''
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  function startPolling() {
    if (pollTimer || disposed) return
    connState.value = 'polling'
    connected.value = false
    const tick = async () => {
      try {
        data.value = await fetchSnapshot()
        lastError.value = ''
      } catch (e: any) {
        setError(`HTTP 轮询取数失败：${e?.message || e}（点击“重试”立即重连实时链路）`)
      }
    }
    void tick()
    pollTimer = setInterval(tick, POLL_INTERVAL_MS)
  }

  function scheduleReconnect() {
    if (manualClose || disposed || reconnectTimer) return
    retrying.value = true
    const delay = Math.min(1000 * 2 ** attempts, MAX_BACKOFF_MS)
    attempts += 1
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      openSocket()
    }, delay)
  }

  function openSocket() {
    if (ws || manualClose || disposed) return
    connState.value = 'connecting'
    let opened = false
    const s = new WebSocket(wsUrl('/ws'))
    ws = s

    s.onopen = () => {
      opened = true
      connected.value = true
      connState.value = 'live'
      retrying.value = false
      attempts = 0
      stopPolling()
      lastError.value = ''
    }
    s.onmessage = (e) => {
      try {
        applyPayload(JSON.parse(e.data))
      } catch (err: any) {
        setError(`实时数据解析失败：${err?.message || err}`)
      }
    }
    s.onerror = () => {
      setError('实时连接(WebSocket)失败，已切换为定时轮询接口取数')
    }
    s.onclose = () => {
      ws = null
      connected.value = false
      if (suppressCloseHandler) {
        suppressCloseHandler = false
        return
      }
      if (!manualClose) {
        // 连上后又断开：退避重连 WS，同时用轮询保证面板有数据
        startPolling()
        scheduleReconnect()
      }
    }
    // 握手超时：从未 open 过则关闭并触发 onclose 流程
    setTimeout(() => {
      if (!opened && ws === s) {
        try { s.close() } catch {}
      }
    }, FETCH_TIMEOUT_MS)
  }

  /** 手动重试入口：取消退避、立即重新拉配置并连接。 */
  async function retry() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    attempts = 0
    try {
      await fetchConfig()
    } catch (e: any) {
      configFetchError.value = `统计口径接口取不到数据：${e?.message || e}，先使用构建时默认口径`
    }
    if (ws) {
      // 主动关闭旧连接，忽略其 onclose（否则会立刻再起一轮轮询/退避）
      suppressCloseHandler = true
      try { ws.close() } catch {}
      ws = null
    }
    stopPolling()
    openSocket()
    // 握手失败时由 onclose 自动回落到轮询
  }

  async function connect() {
    manualClose = false
    try {
      await fetchConfig()
    } catch (e: any) {
      configFetchError.value = `统计口径接口取不到数据：${e?.message || e}，先使用构建时默认口径`
    }
    openSocket()
    // WS 在握手期不可用时 startPolling 由 onclose 触发；
    // 为覆盖极端环境，connect 后短暂确保有一次兜底取数
    setTimeout(() => {
      if (connState.value !== 'live' && !pollTimer && !manualClose) startPolling()
    }, FETCH_TIMEOUT_MS + 200)
  }

  function disconnect() {
    manualClose = true
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    stopPolling()
    ws?.close()
    ws = null
    connected.value = false
    connState.value = 'idle'
  }

  return {
    data, connected, connState, lastError, retrying,
    configError, configFetchError, statConfig,
    connect, disconnect, retry
  }
})
