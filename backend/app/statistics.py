"""产量与效率统计的纯计算口径。

把班次边界、保留时长、OEE 计算从主流程中抽离，全部入参化：
- 同一配置、同一输入 -> 同一输出（改造前后公式未变，默认配置下与历史结果一致）；
- 不再依赖具体机器、端口或进程启动时刻。
"""
from datetime import datetime, timedelta, timezone
from typing import List, Sequence

from . import config


def shift_index(timestamp: float, hours: Sequence[int] = None) -> int:
    """返回时间戳所属班次的序号（按 SHIFT_START_HOURS 划分，跨 0 点衔接）。

    例如边界 [0,8,16]：3 点 -> 班次0；10 点 -> 班次1。
    边界 [8,16,22]：凌晨 2 点 -> 班次2（前一天 22:00 起的跨夜班）。
    """
    hours = sorted(config.SHIFT_START_HOURS if hours is None else hours)
    local_hour = datetime.fromtimestamp(timestamp).hour
    if local_hour < hours[0]:
        return len(hours) - 1  # 跨 0 点：归属最后一个边界开启的夜班
    idx = 0
    for i, h in enumerate(hours):
        if local_hour >= h:
            idx = i
    return idx


def shift_label(timestamp: float, hours: Sequence[int] = None) -> str:
    """人类可读班次标签，如 '08:00-16:00 班次'。"""
    hours = sorted(config.SHIFT_START_HOURS if hours is None else hours)
    idx = shift_index(timestamp, hours)
    start = hours[idx]
    end = hours[(idx + 1) % len(hours)]
    return f"{start:02d}:00-{end:02d}:00 班次"


def current_shift(now: float = None, hours: Sequence[int] = None) -> dict:
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    hours = sorted(config.SHIFT_START_HOURS if hours is None else hours)
    idx = shift_index(now, hours)
    start_hour = hours[idx]
    # 班次起始时间戳（本地日历日 + 边界整点；跨 0 点的夜班回退一天）
    dt = datetime.fromtimestamp(now)
    start_dt = dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    if start_hour > dt.hour:
        start_dt = start_dt - timedelta(days=1)
    start_ts = start_dt.timestamp()
    end_hour = hours[(idx + 1) % len(hours)]
    return {
        "index": idx,
        "label": f"{start_hour:02d}:00-{end_hour:02d}:00 班次",
        "start_hour": start_hour,
        "end_hour": end_hour,
        "start_ts": start_ts,
    }


def filter_retention(log: Sequence[dict], now: float,
                     retention_seconds: float = None) -> List[dict]:
    """按保留时长窗口截取统计记录（兼容改造前按采样点保留的口径）。"""
    retention = config.RETENTION_SECONDS if retention_seconds is None else retention_seconds
    cutoff = now - retention
    return [row for row in log if row["timestamp"] >= cutoff]


def oee_for_device(uptime: float, production_count: int, fault_count: int,
                   quality_rate: float) -> float:
    """单设备 OEE（百分比）。公式与改造前完全一致：可用性×性能×质量。"""
    if uptime == 0:
        return 0.0
    availability = min(1.0, uptime / max(1, uptime + fault_count))
    performance = min(1.0, production_count / max(1, uptime / 2))
    return round(availability * performance * min(1.0, quality_rate) * 100, 1)
