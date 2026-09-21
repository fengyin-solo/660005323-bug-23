import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 统计口径统一从仓库根目录的 .env 读取（后端运行时、前端 dev/build 同源）
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '../', ['VITE_', 'STAT_', 'BACKEND_'])
  const backendPort = env.BACKEND_PORT || '8000'
  const backendTarget = `http://127.0.0.1:${backendPort}`
  const wsTarget = `ws://127.0.0.1:${backendPort}`

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    // 根目录 .env：dev 与 build 取值一致
    envDir: '../',
    envPrefix: ['VITE_', 'STAT_'],
    server: {
      port: 3000,
      proxy: {
        '/api': backendTarget,
        '/ws': { target: wsTarget, ws: true }
      }
    }
  }
})
