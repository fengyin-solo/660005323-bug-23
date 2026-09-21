<template>
  <div class="app-root">
    <header class="top-bar">
      <h1>🏭 数字孪生工厂产线实时监控系统</h1>
      <div class="status-row">
        <span class="ws-dot" :class="{on: store.connected}"></span>
        <span>{{ statusText }}</span>
        <span v-if="store.data?.shift" class="shift-tag">🕘 {{ store.data.shift.label }}</span>
        <span v-if="store.data" class="shift-prod">本班产量: {{ store.data.shift_production ?? 0 }}</span>
        <span class="prod-count">今日产量: {{ store.data?.production || 0 }}</span>
      </div>
    </header>
    <div v-if="store.errorMsg" class="conn-banner">
      <span class="conn-banner-text">⚠️ {{ store.errorMsg }}</span>
      <button class="retry-btn" @click="store.retry()">重试连接</button>
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
const store = useFactoryStore()
const statusText = computed(() => ({
  online: '实时连接中',
  connecting: '正在连接…',
  error: '连接异常',
  idle: '未连接'
}[store.connState] || '连接断开'))
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
.shift-tag{color:#7dd3fc;font-weight:600}
.shift-prod{color:#86efac;font-weight:600}
.conn-banner{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:10px 24px 0;padding:8px 14px;background:#451a1a;border:1px solid #b91c1c;border-radius:6px;color:#fca5a5;font-size:13px}
.retry-btn{background:#b91c1c;color:#fee2e2;border:none;border-radius:4px;padding:4px 14px;font-size:12px;cursor:pointer;white-space:nowrap}
.retry-btn:hover{background:#dc2626}
</style>