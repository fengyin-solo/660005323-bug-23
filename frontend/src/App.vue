<template>
  <div class="app-root">
    <header class="top-bar">
      <h1>🏭 数字孪生工厂产线实时监控系统</h1>
      <div class="status-row">
        <span class="ws-dot" :class="{on: store.connected}"></span>
        <span>{{ connText }}</span>
        <span class="prod-count">班次产量({{ shiftText }}起): {{ store.data?.production || 0 }}</span>
        <button class="retry-btn" :disabled="store.retrying" @click="store.retry()">
          {{ store.retrying ? '重连中…' : '重试' }}
        </button>
      </div>
    </header>
    <div v-if="store.configError" class="alert-bar alert-config">
      ⚙️ {{ store.configError }}
      <button class="retry-btn" @click="reload">重新加载</button>
    </div>
    <div v-if="store.configFetchError" class="alert-bar alert-config">
      📐 {{ store.configFetchError }}
      <button class="retry-btn" :disabled="store.retrying" @click="store.retry()">重试拉取</button>
    </div>
    <div v-if="store.lastError" class="alert-bar alert-data">
      ⚠️ {{ store.lastError }}
      <button class="retry-btn" :disabled="store.retrying" @click="store.retry()">立即重试</button>
    </div>
    <div class="main-grid">
      <div class="scene-col"><FactoryScene /></div>
      <div class="panel-col">
        <DeviceList />
        <AnomalyList />
      </div>
    </div>
    <div class="dashboard-row">
      <OEEChart />
      <TrendPanel />
      <FaultPie />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import FactoryScene from './components/FactoryScene.vue'
import DeviceList from './components/DeviceList.vue'
import AnomalyList from './components/AnomalyList.vue'
import OEEChart from './components/OEEChart.vue'
import TrendPanel from './components/TrendPanel.vue'
import FaultPie from './components/FaultPie.vue'
import { useFactoryStore } from './store/factory'
import { shiftLabel } from './config'
const store = useFactoryStore()

const connText = computed(() => {
  switch (store.connState) {
    case 'live': return '实时连接中'
    case 'connecting': return '正在连接…'
    case 'polling': return '实时断开 · 轮询取数中'
    case 'error': return '连接失败'
    default: return '连接断开'
  }
})

const shiftText = computed(() => {
  const hour = store.data?.shift?.start_hour ?? store.statConfig.shiftStartHour
  return shiftLabel(hour)
})

function reload() { window.location.reload() }

onMounted(() => store.connect())
onUnmounted(() => store.disconnect())
</script>

<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#0a1628;color:#e0e6ed;overflow-x:hidden}
.app-root{min-height:100vh}
.top-bar{display:flex;justify-content:space-between;align-items:center;padding:12px 24px;background:linear-gradient(90deg,#0d2137,#1a3a5c);border-bottom:1px solid #1e3a5f}
.top-bar h1{font-size:1.2rem;color:#64b5f6}
.status-row{display:flex;gap:20px;align-items:center;font-size:13px;color:#94a3b8}
.ws-dot{width:10px;height:10px;border-radius:50%;background:#ef4444}
.ws-dot.on{background:#22c55e;box-shadow:0 0 8px #22c55e}
.prod-count{color:#fbbf24;font-weight:600}
.main-grid{display:grid;grid-template-columns:1fr 360px;gap:12px;padding:12px 24px;min-height:55vh}
.scene-col{background:#0d1b2a;border-radius:12px;border:1px solid #1e3a5f;overflow:hidden}
.panel-col{display:flex;flex-direction:column;gap:12px;overflow-y:auto;max-height:55vh}
.dashboard-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;padding:0 24px 16px}
/* 配置/取数异常提示条（新增，不影响原有面板样式） */
.alert-bar{display:flex;align-items:center;gap:12px;padding:8px 24px;font-size:13px}
.alert-config{background:#3b2f0a;color:#fbbf24;border-bottom:1px solid #7c5a10}
.alert-data{background:#3a1414;color:#fca5a5;border-bottom:1px solid #7f1d1d}
.retry-btn{background:#1e3a5f;color:#e0e6ed;border:1px solid #3b5e85;border-radius:4px;padding:2px 12px;font-size:12px;cursor:pointer}
.retry-btn:hover{background:#274d7a}
.retry-btn:disabled{opacity:.6;cursor:default}
</style>
