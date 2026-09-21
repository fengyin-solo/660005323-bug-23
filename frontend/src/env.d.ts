/// <reference types="vite/client" />
declare module "*.vue" { import type { DefineComponent } from "vue"; const c: DefineComponent<{}, {}, any>; export default c }

// vite.config.ts 从仓库根目录 .env 注入的统计口径（与后端同源）
declare const __STAT_SHIFT_START_HOURS__: string
declare const __STAT_SAMPLE_INTERVAL__: string
declare const __STAT_RETENTION_SECONDS__: string

interface ImportMetaEnv {
  /** 浏览器侧访问后端的地址；留空时走前端同源代理 */
  readonly VITE_API_BASE_URL?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
