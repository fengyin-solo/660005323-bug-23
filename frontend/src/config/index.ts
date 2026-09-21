// 统计口径配置：构建时从仓库根目录 .env 注入（STAT_*），
// 运行时再以 /api/config 拉取后端权威值。默认值与后端保持一致。

export interface StatConfig {
  shiftStartHour: number
  sampleIntervalSec: number
  retentionSec: number
  source: 'build-env' | 'backend'
}

const DEFAULT_SHIFT_START_HOUR = 0
const DEFAULT_SAMPLE_INTERVAL_SEC = 1
const DEFAULT_RETENTION_SEC = 60

function parseIntRange(raw: string | undefined, label: string, fallback: number, lo: number, hi: number, errors: string[]): number {
  if (raw === undefined || raw.trim() === '') return fallback // 缺失走默认
  const v = Number(raw)
  if (!Number.isInteger(v) || v < lo || v > hi) {
    errors.push(`${label}=${raw} 非法，要求 ${lo}~${hi} 的整数`)
    return fallback
  }
  return v
}

function parseFloatRange(raw: string | undefined, label: string, fallback: number, lo: number, hi: number, errors: string[]): number {
  if (raw === undefined || raw.trim() === '') return fallback
  const v = Number(raw)
  if (!Number.isFinite(v) || v < lo || v > hi) {
    errors.push(`${label}=${raw} 非法，要求 ${lo}~${hi} 的数字`)
    return fallback
  }
  return v
}

/** 读取构建期注入的统计口径；非法值通过 errors 返回，由界面提示 + 重试入口兜底。 */
export function loadBuildStatConfig(): { config: StatConfig; errors: string[] } {
  const errors: string[] = []
  const env = import.meta.env
  const config: StatConfig = {
    shiftStartHour: parseIntRange(env.STAT_SHIFT_START_HOUR as string | undefined,
      'STAT_SHIFT_START_HOUR', DEFAULT_SHIFT_START_HOUR, 0, 23, errors),
    sampleIntervalSec: parseFloatRange(env.STAT_SAMPLE_INTERVAL_SEC as string | undefined,
      'STAT_SAMPLE_INTERVAL_SEC', DEFAULT_SAMPLE_INTERVAL_SEC, 0.1, 60, errors),
    retentionSec: parseFloatRange(env.STAT_RETENTION_SEC as string | undefined,
      'STAT_RETENTION_SEC', DEFAULT_RETENTION_SEC, 1, 86400, errors),
    source: 'build-env'
  }
  return { config, errors }
}

/**
 * HTTP / WS 基础地址。
 * - 配置了 VITE_API_BASE（构建期注入）时使用它（独立部署）
 * - 否则同源（dev 下由 Vite 代理转发，换机器/换端口无需改动）
 */
export function apiBase(): string {
  const explicit = (import.meta.env.VITE_API_BASE as string | undefined)?.trim()
  return explicit ? explicit.replace(/\/+$/, '') : ''
}

export function httpUrl(path: string): string {
  return `${apiBase()}${path}`
}

export function wsUrl(path: string): string {
  const base = apiBase()
  if (base) {
    return base.replace(/^http/, 'ws').replace(/\/+$/, '') + path
  }
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}${path}`
}

export function shiftLabel(hour: number): string {
  const h = String(hour).padStart(2, '0')
  return `${h}:00`
}
