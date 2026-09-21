# 数字孪生工厂产线实时监控系统

基于Vue 3 + FastAPI的工厂数字孪生平台，MQTT设备模拟、Three.js 3D产线可视化、WebSocket实时推送、异常检测规则引擎。

## 目标用户
智能制造工程师、工厂运营管理者、工业4.0解决方案顾问

## 技术栈
- 前端: Vue 3 + TypeScript + Vite + Pinia + Element Plus + ECharts + Three.js
- 后端: Python FastAPI + NumPy + SQLite + WebSocket

## 核心功能
1. MQTT设备模拟器：6类工业设备(CNC/机械臂/传送带/AGV/注塑机/质检站)状态与传感器数据模拟
2. Three.js 3D工厂数字孪生场景：设备模型、产线布局、实时状态颜色映射(绿运行/黄待机/红故障/灰离线)
3. WebSocket实时推送设备状态与传感器数据流
4. 异常检测规则引擎：温度/振动/压力多维阈值+滑动窗口趋势检测
5. OEE(设备综合效率)计算：可用性×性能×质量三维指标
6. ECharts实时趋势面板：产量统计、故障分布饼图、设备OEE柱状图

## 统计口径统一配置

产量/效率的三项口径与服务端口统一收拢在仓库根目录的 `.env`（模板见 `.env.example`），
后端运行时与前端 dev/build 均从同一份配置取值：

| 变量 | 含义 | 默认值 | 合法性 |
| --- | --- | --- | --- |
| `STAT_SHIFT_START_HOUR` | 班次边界（班次开始整点） | `0`（零点跨日，等同原"今日产量"） | 0-23 整数 |
| `STAT_SAMPLE_INTERVAL_SEC` | 采样/推送间隔（秒） | `1` | 0.1-60 |
| `STAT_RETENTION_SEC` | 产量日志保留时长（秒） | `60` | 1-86400 |
| `BACKEND_HOST` / `BACKEND_PORT` | 后端监听地址/端口 | `0.0.0.0` / `8000` | 端口 1-65535 |
| `VITE_API_BASE` | 前端访问后端的基址 | 空（dev 走 Vite 代理，部署走同源） | URL 或空 |

取值优先级：进程环境变量 > `.env` 文件 > 内置默认值。配置非法时后端拒绝启动并打印逐项错误；
配置缺失时回退默认值并在日志提示。前端在启动时再拉取 `GET /api/config` 作为权威口径，
取数失败时顶栏会显示原因并提供"重试"入口，同时自动从 WebSocket 退避重连、
期间降级为 HTTP 定时轮询（`/api/devices`、`/api/oee`），面板不会空白。

## 启动方式

```bash
# 后端（端口取自 .env 的 BACKEND_PORT，两种方式等价）
cd backend
python run.py
# 或 uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端（dev 代理与 build 注入均读根目录 .env，换机器/换端口无需改代码）
cd frontend
npm install
npm run dev      # 开发
npm run build    # 构建（口径在构建期注入，运行时再由 /api/config 校准）
```

