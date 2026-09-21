"""统一环境配置。

后端从此模块取统计口径；前端/vite 从仓库根目录同一份 .env 取值（见
frontend/vite.config.ts）。这样班次边界、采样间隔、保留时长在本地开发
与构建时只有一个数据源，换机器/换端口只需改 .env。

取值优先级：进程环境变量 > 仓库根目录 .env > 内置默认值。
内置默认值与改造前的写死口径完全一致，保证统计结果可复现。
"""
import os
from pathlib import Path
from typing import List, Optional


def _read_dotenv(path: Path) -> dict:
    """极简 .env 解析：KEY=VALUE，# 开头为注释，不覆盖已存在的环境变量。"""
    data = {}
    if not path.is_file():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = REPO_ROOT / ".env"
_FILE_VALUES = _read_dotenv(_ENV_FILE)


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name, _FILE_VALUES.get(name, default))
    return val if val not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(
            f"环境配置 {name}={raw!r} 不是合法整数，请检查 {_ENV_FILE}（应为整数秒）"
        )


def _get_float(name: str, default: float) -> float:
    raw = _get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"环境配置 {name}={raw!r} 不是合法数字，请检查 {_ENV_FILE}"
        )


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _parse_shift_hours(raw: str) -> List[int]:
    hours = []
    for part in raw.split(","):
        part = part.strip()
        if part == "":
            continue
        try:
            h = int(part)
        except ValueError:
            raise ValueError(
                f"环境配置 STAT_SHIFT_START_HOURS={raw!r} 含非整数项 {part!r}，"
                f"请检查 {_ENV_FILE}（示例：0,8,16）"
            )
        if not 0 <= h < 24:
            raise ValueError(
                f"班次边界小时必须在 0~23 之间，收到 {h}（STAT_SHIFT_START_HOURS={raw!r}）"
            )
        hours.append(h)
    if not hours:
        raise ValueError(
            f"STAT_SHIFT_START_HOURS 至少需要一个班次边界，请检查 {_ENV_FILE}（示例：0,8,16）"
        )
    hours = sorted(set(hours))
    if len(hours) < 1:
        raise ValueError("班次边界解析后为空，请检查 STAT_SHIFT_START_HOURS")
    return hours


# ---- 服务监听 ----
BACKEND_HOST: str = _get("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT: int = _get_int("BACKEND_PORT", 8000)
if not 1 <= BACKEND_PORT <= 65535:
    raise ValueError(f"BACKEND_PORT 必须在 1~65535 之间，收到 {BACKEND_PORT}")
FRONTEND_PORT: int = _get_int("FRONTEND_PORT", 3000)
if not 1 <= FRONTEND_PORT <= 65535:
    raise ValueError(f"FRONTEND_PORT 必须在 1~65535 之间，收到 {FRONTEND_PORT}")

# ---- 统计口径 ----
SHIFT_START_HOURS: List[int] = _parse_shift_hours(_get("STAT_SHIFT_START_HOURS", "0,8,16"))
SAMPLE_INTERVAL: float = _get_float("STAT_SAMPLE_INTERVAL", 1.0)
if SAMPLE_INTERVAL <= 0:
    raise ValueError(f"STAT_SAMPLE_INTERVAL 必须为正数，收到 {SAMPLE_INTERVAL}")
RETENTION_SECONDS: float = _get_float("STAT_RETENTION_SECONDS", 60.0)
if RETENTION_SECONDS <= 0:
    raise ValueError(f"STAT_RETENTION_SECONDS 必须为正数，收到 {RETENTION_SECONDS}")

PRODUCTION_LOG_MAXLEN: int = _get_int("PRODUCTION_LOG_MAXLEN", 10000)
ANOMALY_LOG_MAXLEN: int = _get_int("ANOMALY_LOG_MAXLEN", 2000)

# ---- 模拟器 ----
SIMULATOR_ENABLED: bool = _get_bool("SIMULATOR_ENABLED", True)
_seed_raw = _get("STAT_RANDOM_SEED", "")
RANDOM_SEED: Optional[int] = None
if _seed_raw:
    try:
        RANDOM_SEED = int(_seed_raw)
    except ValueError:
        raise ValueError(f"STAT_RANDOM_SEED={_seed_raw!r} 不是合法整数（留空表示随机）")

ENV_FILE_EXISTS = _ENV_FILE.is_file()


def config_snapshot() -> dict:
    """提供给 /api/config：把统计口径告诉前端，便于核对是否与历史一致。"""
    return {
        "shift_start_hours": SHIFT_START_HOURS,
        "sample_interval": SAMPLE_INTERVAL,
        "retention_seconds": RETENTION_SECONDS,
        "production_log_maxlen": PRODUCTION_LOG_MAXLEN,
        "anomaly_log_maxlen": ANOMALY_LOG_MAXLEN,
        "random_seed": RANDOM_SEED,
    }


def startup_banner() -> str:
    lines = [
        "=" * 64,
        "数字孪生工厂 · 统计口径配置",
        f"  配置文件: {_ENV_FILE}"
        + ("" if ENV_FILE_EXISTS else "  [缺失，使用内置默认值；建议复制 .env.example 为 .env]"),
        f"  班次边界(整点): {SHIFT_START_HOURS}",
        f"  采样间隔: {SAMPLE_INTERVAL}s",
        f"  保留时长: {RETENTION_SECONDS}s（产量日志上限 {PRODUCTION_LOG_MAXLEN} 条）",
        f"  模拟器: {'开启' if SIMULATOR_ENABLED else '关闭'}",
        f"  随机种子: {RANDOM_SEED if RANDOM_SEED is not None else '未设置(每次随机)'}",
        f"  监听: http://{BACKEND_HOST}:{BACKEND_PORT}",
        "=" * 64,
    ]
    return "\n".join(lines)
