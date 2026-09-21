from __future__ import annotations

import asyncio, math, random, time, json, threading
from collections import defaultdict, deque
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:  # numpy 不可用时仍可启动（趋势检测退化为纯 Python 计算）
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from app.config import settings

app = FastAPI(title="Digital Twin Factory Monitor")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DEVICE_TYPES = ["CNC", "RobotArm", "Conveyor", "AGV", "InjectionMolding", "QCStation"]
STATUSES = ["RUNNING", "IDLE", "FAULT", "OFFLINE"]
ACTIVE_CLIENTS: list[WebSocket] = []
SIMULATOR_RUNNING = True
# 主事件循环：模拟器在子线程里推送 WS 时必须通过它调度协程
MAIN_LOOP: asyncio.AbstractEventLoop | None = None


class DeviceState:
    def __init__(self, did: int, dtype: str, x: float, y: float, z: float):
        self.id = did
        self.type = dtype
        self.status = "RUNNING"
        self.position = [x, y, z]
        self.temperature = random.uniform(35, 45)
        self.vibration = random.uniform(0.1, 1.5)
        self.pressure = random.uniform(0.8, 1.2)
        self.production_count = 0
        self.fault_count = 0
        self.uptime = 0.0
        self.cycle_time = random.uniform(2, 8)
        self.quality_rate = random.uniform(0.95, 0.995)

    def to_dict(self):
        return {
            "id": self.id, "type": self.type, "status": self.status,
            "position": self.position, "temperature": round(self.temperature, 2),
            "vibration": round(self.vibration, 3), "pressure": round(self.pressure, 2),
            "production_count": self.production_count, "fault_count": self.fault_count,
            "uptime": round(self.uptime, 2), "quality_rate": round(self.quality_rate, 3)
        }

devices = {i: DeviceState(i, random.choice(DEVICE_TYPES),
                          random.uniform(-5, 5), 0.5, random.uniform(-5, 5)) for i in range(1, 13)}

# 产量日志按配置的保留时长做时间裁剪（deque 只保留最多 retention/interval+余量 条）
_retention_capacity = max(1, int(settings.retention_sec / settings.sample_interval_sec) + 2)
production_log: deque = deque(maxlen=_retention_capacity)
anomaly_log: deque = deque(maxlen=500)


def current_shift_start(now: float | None = None) -> float:
    """最近一个班次边界的 unix 时间戳（按本地时区、配置的班次开始整点）。"""
    t = time.time() if now is None else now
    local = time.localtime(t)
    today_boundary = time.mktime((local.tm_year, local.tm_mon, local.tm_mday,
                                  settings.shift_start_hour, 0, 0, 0, 0, -1))
    if t >= today_boundary:
        return today_boundary
    yesterday = time.localtime(today_boundary - 86400)
    return time.mktime((yesterday.tm_year, yesterday.tm_mon, yesterday.tm_mday,
                        settings.shift_start_hour, 0, 0, 0, 0, -1))


# 当前班次开始时的总产量基线，用于计算“本班次产量”
shift_base_total = 0
shift_start_ts = current_shift_start()


class AnomalyRules:
    def __init__(self):
        self.rules = [
            {"name": "高温告警", "field": "temperature", "threshold": 48, "op": "gt"},
            {"name": "振动超标", "field": "vibration", "threshold": 2.0, "op": "gt"},
            {"name": "压力异常", "field": "pressure", "threshold": 1.5, "op": "gt"},
        ]
        self.windows = defaultdict(lambda: deque(maxlen=10))

    def check(self, dev: DeviceState):
        triggers = []
        for rule in self.rules:
            val = getattr(dev, rule["field"])
            if (rule["op"] == "gt" and val > rule["threshold"]) or (rule["op"] == "lt" and val < rule["threshold"]):
                triggers.append({"device_id": dev.id, "rule": rule["name"],
                                 "value": round(val, 3), "threshold": rule["threshold"]})

        # sliding window trend
        key = f"{dev.id}_temp"
        self.windows[key].append(dev.temperature)
        if len(self.windows[key]) >= 8:
            vals = list(self.windows[key])
            first4, last4 = vals[:4], vals[-4:]
            if np is not None:
                rising = np.mean(last4) - np.mean(first4) > 3
                last_mean = float(np.mean(last4))
            else:
                rising = sum(last4) / 4 - sum(first4) / 4 > 3
                last_mean = sum(last4) / 4
            if rising:
                triggers.append({"device_id": dev.id, "rule": "温度趋势上升", "value": round(last_mean, 2), "threshold": ">3°C/周期"})

        if triggers:
            anomaly_log.append({"timestamp": time.time(), "triggers": triggers, "device_type": dev.type})
        return triggers

rules_engine = AnomalyRules()


def shift_production() -> int:
    """本班次内的产量（跨过配置的班次边界时归零重计）。"""
    return sum(d.production_count for d in devices.values()) - shift_base_total


def trim_production_log(now: float) -> None:
    cutoff = now - settings.retention_sec
    while production_log and production_log[0]["timestamp"] < cutoff:
        production_log.popleft()


async def broadcast(message: str) -> None:
    if not ACTIVE_CLIENTS:
        return
    dead = []
    for ws in list(ACTIVE_CLIENTS):
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in ACTIVE_CLIENTS:
            ACTIVE_CLIENTS.remove(ws)


def simulate():
    global shift_base_total, shift_start_ts
    next_tick = time.monotonic()
    while SIMULATOR_RUNNING:
        # 固定节拍：以单调时钟补偿循环耗时，保证采样间隔与配置一致（修复耗时漂移）
        next_tick += settings.sample_interval_sec
        sleep_s = next_tick - time.monotonic()
        if sleep_s > 0:
            time.sleep(sleep_s)
        else:
            next_tick = time.monotonic()

        now = time.time()

        # 跨过班次边界：把当前总产量记为新班次基线
        boundary = current_shift_start(now)
        if boundary != shift_start_ts:
            shift_start_ts = boundary
            shift_base_total = sum(d.production_count for d in devices.values())

        for dev in devices.values():
            drift = 0.1 * math.sin(now * 0.5 + dev.id)
            noise = random.gauss(0, 0.3)
            dev.temperature = max(25, min(65, dev.temperature + drift + noise))

            v_drift = 0.02 * math.sin(now * 0.3 + dev.id * 0.7)
            dev.vibration = max(0, min(3, dev.vibration + v_drift + random.gauss(0, 0.05)))

            dev.pressure = max(0.5, min(2, dev.pressure + random.gauss(0, 0.02)))

            if random.random() < 0.015:
                dev.status = "FAULT"
                dev.fault_count += 1
            elif random.random() < 0.03 and dev.status == "FAULT":
                dev.status = "RUNNING"

            if dev.status == "RUNNING":
                if random.random() < 0.4:
                    dev.production_count += 1
                dev.uptime += settings.sample_interval_sec

            triggers = rules_engine.check(dev)
            if triggers and dev.status != "FAULT" and random.random() < 0.3:
                dev.status = "FAULT"

        total = sum(d.production_count for d in devices.values())
        production_log.append({"timestamp": now, "count": total})
        trim_production_log(now)

        payload = {
            "devices": [d.to_dict() for d in devices.values()],
            "production": shift_production(),
            "anomalies": list(anomaly_log)[-5:] if anomaly_log else [],
            "oee": calculate_oee(),
            "shift": {"start_hour": settings.shift_start_hour, "start_ts": shift_start_ts},
        }
        try:
            message = json.dumps(payload)
        except (TypeError, ValueError):
            continue

        if MAIN_LOOP is not None and ACTIVE_CLIENTS:
            try:
                asyncio.run_coroutine_threadsafe(broadcast(message), MAIN_LOOP)
            except RuntimeError:
                pass  # 事件循环已关闭（停机中）


def calculate_oee():
    oee_list = []
    for dev in devices.values():
        if dev.uptime == 0:
            continue
        availability = min(1.0, dev.uptime / max(1, dev.uptime + dev.fault_count))
        performance = min(1.0, dev.production_count / max(1, dev.uptime / 2))
        quality = dev.quality_rate
        oee = round(availability * performance * quality * 100, 1)
        oee_list.append({"id": dev.id, "type": dev.type, "oee": oee,
                         "availability": round(availability * 100, 1),
                         "performance": round(performance * 100, 1),
                         "quality": round(quality * 100, 1)})
    return oee_list


class OEEAnalysis(BaseModel):
    availability: float
    performance: float
    quality: float


@app.on_event("startup")
async def startup():
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    t = threading.Thread(target=simulate, daemon=True)
    t.start()


@app.get("/api/config")
def get_config():
    """前端启动时拉取统计口径，作为环境变量之外的权威来源。"""
    return {"config": settings.public(), "source": settings.config_source}


@app.get("/api/devices")
def get_devices():
    return {"devices": [d.to_dict() for d in devices.values()],
            "anomalies": list(anomaly_log)[-10:],
            "shift_production": shift_production(),
            "shift": {"start_hour": settings.shift_start_hour, "start_ts": shift_start_ts}}


@app.get("/api/oee")
def get_oee():
    return {"oee": calculate_oee()}


@app.get("/api/production")
def get_production():
    trim_production_log(time.time())
    return {"log": list(production_log)}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    ACTIVE_CLIENTS.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in ACTIVE_CLIENTS:
            ACTIVE_CLIENTS.remove(websocket)


@app.on_event("shutdown")
async def shutdown():
    global SIMULATOR_RUNNING
    SIMULATOR_RUNNING = False
