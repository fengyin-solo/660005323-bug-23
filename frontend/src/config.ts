// 前端运行时配置：地址来自 .env 的 VITE_API_BASE_URL（留空则同源，由 vite 代理
// 或反向代理转发，换机器/换端口无需改代码）；统计口径来自 vite 注入的同一 .env。

function parseHours(raw: string): number[] {
  return raw.split(',').map((s) => parseInt(s.trim(), 10)).filter((h) => !Number.isNaN(h))
}

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

export function apiUrl(path: string): string {
  return `${apiBaseUrl}${path}`
}

export function wsUrl(path = '/ws'): string {
  if (apiBaseUrl) {
    const u = new URL(apiBaseUrl)
    return `${u.protocol === 'https:' ? 'wss' : 'ws'}://${u.host}${path}`
  }
  // 同源：协议升级，端口跟随当前页面，不再写死 8000
  return `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}${path}`
}

export const statConfig = {
  shiftStartHours: parseHours(__STAT_SHIFT_START_HOURS__ || '0,8,16'),
  sampleInterval: parseFloat(__STAT_SAMPLE_INTERVAL__ || '1'),
  retentionSeconds: parseFloat(__STAT_RETENTION_SECONDS__ || '60')
}
