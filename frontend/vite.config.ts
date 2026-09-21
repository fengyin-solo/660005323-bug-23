import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 本地开发与构建统一从仓库根目录的 .env 取值（与后端同一份配置），
// 换机器/换端口只需改 .env，不再改代码。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd() + '/..', '')
  const frontendPort = parseInt(env.FRONTEND_PORT || '3000', 10)
  const backendPort = parseInt(env.BACKEND_PORT || '8000', 10)
  const backendTarget = env.BACKEND_TARGET || `http://127.0.0.1:${backendPort}`

  // 仅把统计口径相关字段注入前端（VITE_ 前缀的按惯例自动暴露）
  const statDefines = {
    __STAT_SHIFT_START_HOURS__: JSON.stringify(env.STAT_SHIFT_START_HOURS || '0,8,16'),
    __STAT_SAMPLE_INTERVAL__: JSON.stringify(env.STAT_SAMPLE_INTERVAL || '1'),
    __STAT_RETENTION_SECONDS__: JSON.stringify(env.STAT_RETENTION_SECONDS || '60')
  }

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    define: statDefines,
    server: {
      port: frontendPort,
      proxy: {
        '/api': backendTarget,
        '/ws': { target: backendTarget.replace(/^http/, 'ws'), ws: true }
      }
    },
    preview: {
      port: frontendPort,
      proxy: {
        '/api': backendTarget,
        '/ws': { target: backendTarget.replace(/^http/, 'ws'), ws: true }
      }
    }
  }
})
