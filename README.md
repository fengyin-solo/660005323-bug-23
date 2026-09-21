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

## 统一环境配置

班次边界、采样间隔、保留时长等统计口径收拢在仓库根目录**同一份 `.env`**，
本地开发与构建均从它取值，换机器/换端口只改这一个文件：

```bash
cp .env.example .env   # 首次使用；.env 不入库，按机器自行调整
```

| 变量 | 含义 | 默认值（与历史口径一致） |
| --- | --- | --- |
| `BACKEND_HOST` / `BACKEND_PORT` | 后端监听地址/端口 | `0.0.0.0` / `8000` |
| `FRONTEND_PORT` | 前端 dev/preview 端口 | `3000` |
| `VITE_API_BASE_URL` | 浏览器访问后端地址；**留空走同源代理**，换端口无需改动 | 空 |
| `STAT_SHIFT_START_HOURS` | 班次边界（24小时制整点，逗号分隔，支持跨 0 点） | `0,8,16` |
| `STAT_SAMPLE_INTERVAL` | 采样/推送间隔（秒） | `1` |
| `STAT_RETENTION_SECONDS` | 产量/效率历史保留时长（秒） | `60`（=历史 60 个采样点） |
| `PRODUCTION_LOG_MAXLEN` / `ANOMALY_LOG_MAXLEN` | 内存兜底上限（条） | `10000` / `2000` |
| `STAT_RANDOM_SEED` | 随机种子，留空随机；填整数可复现同一套统计结果 | 空 |

缺配置时使用内置默认值并在启动横幅中提示；配置非法会在启动时直接报错并指出变量名。
接口不可达时前端顶部红条给出原因与「重试连接」按钮，同时按指数退避自动重连。
当前生效口径可通过 `GET /api/config` 核对。

## 启动

```bash
# 后端（监听地址/端口与统计口径均从 .env 读取）
cd backend
pip install -r requirements.txt
python -m app.main

# 前端（dev 与 build 均从根目录 .env 取值）
cd frontend
npm install
npm run dev      # 开发：/api、/ws 同源代理到后端
npm run build    # 构建：统计口径在构建期内联进产物
```

## 测试

```bash
cd backend && python -m unittest app.tests.test_statistics -v
```

