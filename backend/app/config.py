"""统一配置：产量/效率统计口径（班次边界、采样间隔、保留时长）与服务端口。

取值优先级：进程环境变量 > 仓库根目录 .env 文件 > 内置默认值。
默认值与改造前写死的口径一致（0 点跨日 / 1 秒采样 / 保留 60 秒 / 8000 端口），
保证同一套启动方式下统计结果不变。
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"

DEFAULTS = {
    "STAT_SHIFT_START_HOUR": "0",       # 班次开始整点 0-23
    "STAT_SAMPLE_INTERVAL_SEC": "1",    # 采样/推送间隔（秒）
    "STAT_RETENTION_SEC": "60",         # 产量日志保留时长（秒）
    "BACKEND_HOST": "0.0.0.0",
    "BACKEND_PORT": "8000",
}


class Settings:
    def __init__(self, shift_start_hour: int, sample_interval_sec: float,
                 retention_sec: float, backend_host: str, backend_port: int,
                 config_source: str):
        self.shift_start_hour = shift_start_hour
        self.sample_interval_sec = sample_interval_sec
        self.retention_sec = retention_sec
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.config_source = config_source  # env_file / environment / defaults ...

    def public(self) -> dict:
        """暴露给前端 /api/config 的统计口径。"""
        return {
            "shift_start_hour": self.shift_start_hour,
            "sample_interval_sec": self.sample_interval_sec,
            "retention_sec": self.retention_sec,
        }


def _parse_env_file(path: Path) -> dict:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _fail(messages: list) -> None:
    print("=" * 60, file=sys.stderr)
    print("统计配置加载失败，请检查 .env（模板见 .env.example）：", file=sys.stderr)
    for m in messages:
        print(f"  - {m}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    raise SystemExit(1)


def load_settings() -> Settings:
    errors, warnings = [], []

    file_values = {}
    if ENV_FILE.exists():
        try:
            file_values = _parse_env_file(ENV_FILE)
        except OSError as exc:
            _fail([f"无法读取配置文件 {ENV_FILE}: {exc}"])
    else:
        warnings.append(
            f"未找到配置文件 {ENV_FILE}，统计口径使用内置默认值；"
            f"如需固化配置请执行: cp .env.example .env"
        )

    merged = dict(DEFAULTS)
    merged.update(file_values)
    env_overrides = {k: v for k, v in os.environ.items() if k in DEFAULTS}
    merged.update(env_overrides)

    for key, default in DEFAULTS.items():
        if key not in file_values and key not in env_overrides:
            warnings.append(f"配置项 {key} 缺失，使用默认值 {default}")

    def as_int(key: str, lo: int, hi: int) -> int:
        raw = merged[key].strip()
        try:
            val = int(raw)
        except ValueError:
            errors.append(f"{key}={raw!r} 不是合法整数，要求 {lo}~{hi} 之间的整数")
            return lo
        if not lo <= val <= hi:
            errors.append(f"{key}={val} 超出允许范围 [{lo}, {hi}]")
        return val

    def as_float(key: str, lo: float, hi: float) -> float:
        raw = merged[key].strip()
        try:
            val = float(raw)
        except ValueError:
            errors.append(f"{key}={raw!r} 不是合法数字，要求 {lo}~{hi} 之间")
            return lo
        if not lo <= val <= hi:
            errors.append(f"{key}={val} 超出允许范围 [{lo}, {hi}]")
        return val

    shift_hour = as_int("STAT_SHIFT_START_HOUR", 0, 23)
    interval = as_float("STAT_SAMPLE_INTERVAL_SEC", 0.1, 60.0)
    retention = as_float("STAT_RETENTION_SEC", 1.0, 24 * 3600.0)
    port = as_int("BACKEND_PORT", 1, 65535)
    host = merged["BACKEND_HOST"].strip() or "0.0.0.0"

    if errors:
        _fail(errors)

    if ENV_FILE.exists() and env_overrides:
        source = "env_file+environment"
    elif ENV_FILE.exists():
        source = "env_file"
    elif env_overrides:
        source = "environment"
    else:
        source = "defaults"

    for w in warnings:
        print(f"[config] {w}", file=sys.stderr)
    print(
        f"[config] 统计口径已加载(source={source}): 班次边界={shift_hour}:00, "
        f"采样间隔={interval}s, 保留时长={retention}s, 服务={host}:{port}",
        file=sys.stderr,
    )

    return Settings(shift_hour, interval, retention, host, port, source)


settings = load_settings()
