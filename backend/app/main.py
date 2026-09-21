import asyncio
import json
import logging
import math
import random
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import numpy as np

from . import config, statistics

app = FastAPI(title="Digital Twin Factory Monitor")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("digital_twin")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DEVICE_TYPES = ["CNC", "RobotArm", "Conveyor", "AGV", "InjectionMolding", "QCStation"]
STATUSES = ["RUNNING", "IDLE", "FAULT", "OFFLINE"]
ACTIVE_CLIENTS: list = []
SIMULATOR_RUNNING = True

# 模拟器线程与 asyncio 事件循环的桥接（startup 时捕获主循环）。
# 改造前这里直接 asyncio.get_event_loop()，模拟器线程内没有事件循环，
# 每次推送都抛错并被裸 except 吞掉，是"耗时异常/收不到数据"的根因。
_event_loop: asyncio.AbstractEventLoop = None

if config.RANDOM_SEED is not None:
    random.seed(config.RANDOM_SEED)
    np.random.seed(config.RANDOM_SEED)


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

# 有界历史日志：保留时长窗口在查询时按时间过滤，maxlen 作为内存兜底，
# 不再像改造前那样无界增长导致长跑后耗时异常。
production_log = deque(maxlen=config.PRODUCTION_LOG_MAXLEN)
anomaly_log = deque(maxlen=config.ANOMALY_LOG_MAXLEN)

# 各班次开始时的累计产量基线：{shift_index: baseline_total}
# 本班产量 = 当前累计总产量 - 本班开始时基线（重启后仍可从日志重建）。
shift_baseline: dict = {}


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
            if (rule["op"] == "gt" and val > rule["threshold"]) or \
               (rule["op"] == "lt" and val < rule["threshold"]):
                triggers.append({"device_id": dev.id, "rule": rule["name"],
                                 "value": round(val, 3), "threshold": rule["threshold"]})

        # sliding window trend
        key = f"{dev.id}_temp"
        self.windows[key].append(dev.temperature)
        if len(self.windows[key]) >= 8:
            vals = list(self.windows[key])
            if np.mean(vals[-4:]) - np.mean(vals[:4]) > 3:
                triggers.append({"device_id": dev.id, "rule": "温度趋势上升",
                                 "value": round(np.mean(vals[-4:]), 2), "threshold": ">3°C/周期"})

        if triggers:
            anomaly_log.append({"timestamp": time.time(), "triggers": triggers,
                                "device_type": dev.type})
        return triggers


rules_engine = AnomalyRules()


def total_production() -> int:
    return sum(d.production_count for d in devices.values())


def shift_production(now: float = None) -> int:
    """当前班次内的产量。首次进入某班次时记录当时的累计总量作为基线。"""
    now = now if now is not None else time.time()
    shift = statistics.current_shift(now)
    idx = shift["index"]
    if idx not in shift_baseline:
        # 重启恢复：若该班次已有日志，用第一条日志之前的累计值近似基线
        prev = [r for r in production_log if statistics.shift_index(r["timestamp"]) == idx]
        shift_baseline[idx] = prev[0]["count"] if prev else total_production()
    return max(0, total_production() - shift_baseline[idx])


def simulate():
    # 采样间隔取自配置（改造前写死 time.sleep(1)）
    while SIMULATOR_RUNNING:
        tick_start = time.monotonic()
        for dev in devices.values():
            drift = 0.1 * math.sin(time.time() * 0.5 + dev.id)
            noise = random.gauss(0, 0.3)
            dev.temperature = max(25, min(65, dev.temperature + drift + noise))

            v_drift = 0.02 * math.sin(time.time() * 0.3 + dev.id * 0.7)
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
                # uptime 以秒累计，与采样间隔绑定（改造前固定 +1 对应 1s 采样）
                dev.uptime += config.SAMPLE_INTERVAL

            triggers = rules_engine.check(dev)
            if triggers and dev.status != "FAULT" and random.random() < 0.3:
                dev.status = "FAULT"

        now = time.time()
        production_log.append({"timestamp": now, "count": total_production()})

        payload = build_payload(now)
        try:
            msg = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            logger.warning("序列化统计数据失败，已跳过本周期: %s", exc)
            msg = None

        if msg is not None:
            dead = []
            for ws in ACTIVE_CLIENTS:
                try:
                    fut = asyncio.run_coroutine_threadsafe(ws.send_text(msg), _event_loop)

                    def _on_done(future, socket=ws):
                        if future.exception() is not None:
                            dead.append(socket)

                    fut.add_done_callback(_on_done)
                except RuntimeError:
                    dead.append(ws)
            for ws in dead:
                if ws in ACTIVE_CLIENTS:
                    ACTIVE_CLIENTS.remove(ws)

        # 按配置的采样间隔等待（补偿本周期耗时，避免漂移）
        elapsed = time.monotonic() - tick_start
        time.sleep(max(0.0, config.SAMPLE_INTERVAL - elapsed))


def build_payload(now: float = None) -> dict:
    now = now if now is not None else time.time()
    shift = statistics.current_shift(now)
    return {
        "devices": [d.to_dict() for d in devices.values()],
        # production 保持改造前语义：进程累计总量（"今日产量"面板口径不变）
        "production": total_production(),
        # 新增：按配置的班次边界统计的本班产量
        "shift_production": shift_production(now),
        "shift": shift,
        "anomalies": list(anomaly_log)[-5:] if anomaly_log else [],
        "oee": calculate_oee(),
        "server_time": now,
    }


def calculate_oee():
    """OEE 公式与改造前完全一致（仅从 statistics 复用同一实现）。"""
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
    global _event_loop
    _event_loop = asyncio.get_running_loop()
    for line in config.startup_banner().splitlines():
        logger.info(line)
    if config.SIMULATOR_ENABLED:
        t = threading.Thread(target=simulate, daemon=True)
        t.start()
    else:
        logger.info("SIMULATOR_ENABLED=false，未启动内置模拟器（等待外部数据接入）")


@app.get("/api/health")
def health():
    return {"status": "ok", "time": time.time()}


@app.get("/api/config")
def get_config():
    """向前端公开统计口径，便于核对是否与历史数据一致。"""
    return config.config_snapshot()


@app.get("/api/devices")
def get_devices():
    return {"devices": [d.to_dict() for d in devices.values()],
            "anomalies": list(anomaly_log)[-10:]}


@app.get("/api/oee")
def get_oee():
    return {"oee": calculate_oee()}


@app.get("/api/production")
def get_production():
    # 保留时长取自配置（改造前写死 [-60:]，即 60 个 1s 采样点）
    window = statistics.filter_retention(list(production_log), time.time())
    return {"log": window, "retention_seconds": config.RETENTION_SECONDS}


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
    finally:
        if websocket in ACTIVE_CLIENTS:
            ACTIVE_CLIENTS.remove(websocket)


@app.on_event("shutdown")
async def shutdown():
    global SIMULATOR_RUNNING
    SIMULATOR_RUNNING = False


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.BACKEND_HOST, port=config.BACKEND_PORT)
