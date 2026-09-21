/// <reference types="vite/client" />
declare module "*.vue" { import type { DefineComponent } from "vue"; const c: DefineComponent<{}, {}, any>; export default c }

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly STAT_SHIFT_START_HOUR?: string
  readonly STAT_SAMPLE_INTERVAL_SEC?: string
  readonly STAT_RETENTION_SEC?: string
  readonly BACKEND_PORT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
