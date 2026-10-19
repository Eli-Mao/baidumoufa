"""统一数据契约的唯一实现。分区：川谷（契约层，冻结接口）。

本模块是全项目**唯一**的数据读写入口。规则：

1. 任何人不得绕过本模块直接 ``pd.read_csv`` 业务文件；所有读写都走这里。
2. 需要新增字段时，改本文件的 SCHEMA 并同步更新 ``docs/data_contract.md``，
   改动需四人在群里确认——因为这会同时影响四个人的模块。
3. 列名或类型不符时立即抛 :class:`SchemaError`，绝不带病往下跑。

重点：TLE 编号解码
    原始 ``轨道.txt`` 中有 108 颗卫星的编号使用 Alpha-5 编码（A/T 前缀），
    例如 ``A0045`` -> 100045、``T0288`` -> 270288。
    直接 ``int(token)`` 会抛异常或被静默跳过，导致这些星在与优先级表关联时丢失。
    统一使用 :func:`decode_satnum`。
"""

from __future__ import annotations

import csv
import datetime as _dt
import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from . import config

# --------------------------------------------------------------------------
# 异常
# --------------------------------------------------------------------------


class SchemaError(ValueError):
    """契约被破坏（缺列 / 类型不符 / 必填值为空）。"""


# --------------------------------------------------------------------------
# Alpha-5 编号解码
# --------------------------------------------------------------------------

# Alpha-5 字表：A=10 ... Z=33，跳过字母 I 和 O
ALPHA5_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def decode_satnum(token: str) -> int:
    """把 TLE 的 5 位编号字段解码成整数 NORAD 编号。

    >>> decode_satnum("50574")
    50574
    >>> decode_satnum("A0045")
    100045
    >>> decode_satnum("T0288")
    270288
    """
    token = (token or "").strip()
    if not token:
        raise SchemaError("空的 TLE 编号字段")
    if token[0].isdigit():
        if not token.isdigit():
            raise SchemaError(f"非法 TLE 编号: {token!r}")
        return int(token)
    head = token[0].upper()
    if head not in ALPHA5_CHARS:
        raise SchemaError(f"非法 Alpha-5 首字母: {token!r}")
    # TLE 的编号字段是定宽 5 字符：1 个字母 + 4 位数字
    body = token[1:]
    if len(token) != 5 or not body.isdigit():
        raise SchemaError(f"非法 Alpha-5 编号（应为 1 字母 + 4 数字）: {token!r}")
    return (ALPHA5_CHARS.index(head) + 10) * 10000 + int(body)


def encode_satnum(sat_id: int) -> str:
    """反向编码，便于与原始文件比对（仅用于自检）。"""
    if sat_id < 100000:
        return f"{sat_id:05d}"
    head_index = sat_id // 10000 - 10
    if not 0 <= head_index < len(ALPHA5_CHARS):
        raise SchemaError(f"编号超出 Alpha-5 可表示范围: {sat_id}")
    return f"{ALPHA5_CHARS[head_index]}{sat_id % 10000:04d}"


# --------------------------------------------------------------------------
# 契约定义
# --------------------------------------------------------------------------
# 每列写作 (kind, required_non_null)，kind ∈ {"int", "float", "str"}
# kind 只做"类别"校验，不做严格 dtype 校验，避免 pandas 版本差异导致的误报。

SCHEMA_STATIONS: dict[str, tuple[str, bool]] = {
    "station_id": ("int", True),
    "lon_deg": ("float", True),      # 东经为正
    "lat_deg": ("float", True),      # 北纬为正
    "alt_m": ("float", True),
    "min_elev_deg": ("float", True),
    "max_elev_deg": ("float", True),
}

SCHEMA_SAT_META: dict[str, tuple[str, bool]] = {
    "sat_id": ("int", True),          # 解码后的整数 NORAD 编号
    "name": ("str", True),
    "priority": ("str", True),        # high / mid / low
    "priority_score": ("int", True),  # 5 / 3 / 2
    "tle_epoch_utc": ("str", True),   # ISO8601
}

# ★ 窗口表是楼心荡的产出、也是全队唯一的数据源。字段不可随意删改。
SCHEMA_WINDOWS: dict[str, tuple[str, bool]] = {
    "window_id": ("int", True),
    "station_id": ("int", True),
    "sat_id": ("int", True),
    "priority": ("str", True),
    "priority_score": ("int", True),
    "t_start_s": ("float", True),   # 相对规划期起点 t0 的秒
    "t_end_s": ("float", True),
    "dur_s": ("float", True),       # = t_end_s - t_start_s
    "t_start_utc": ("str", True),
    "t_end_utc": ("str", True),
    "max_elev_deg": ("float", True),
}

# ★ 计划表是 Iceswing 的产出、Priime 评分的输入。
SCHEMA_PLAN: dict[str, tuple[str, bool]] = {
    "task_id": ("int", True),
    "station_id": ("int", True),
    "sat_id": ("int", True),
    "priority": ("str", True),
    "priority_score": ("int", True),
    "t_start_s": ("float", True),
    "t_end_s": ("float", True),
    "dur_s": ("float", True),
    "duration_score": ("float", True),  # 由 rules.duration_score 计算
}

SCHEMAS: dict[str, dict[str, tuple[str, bool]]] = {
    "stations": SCHEMA_STATIONS,
    "sat_meta": SCHEMA_SAT_META,
    "windows": SCHEMA_WINDOWS,
    "plan": SCHEMA_PLAN,
}

_KIND_CHECK = {
    "int": lambda s: pd.api.types.is_integer_dtype(s) or pd.api.types.is_float_dtype(s),
    "float": lambda s: pd.api.types.is_numeric_dtype(s),
    "str": lambda s: pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s),
}

_PD_DTYPE = {"int": "int64", "float": "float64", "str": "object"}


def validate_frame(df: pd.DataFrame, schema_name: str, *, allow_extra: bool = True) -> pd.DataFrame:
    """校验 DataFrame 是否满足契约，不符则抛 :class:`SchemaError`。"""
    if schema_name not in SCHEMAS:
        raise SchemaError(f"未知契约: {schema_name}")
    schema = SCHEMAS[schema_name]

    missing = [c for c in schema if c not in df.columns]
    if missing:
        raise SchemaError(f"[{schema_name}] 缺少必需列: {missing}；实际列为 {list(df.columns)}")

    if not allow_extra:
        extra = [c for c in df.columns if c not in schema]
        if extra:
            raise SchemaError(f"[{schema_name}] 出现未登记列: {extra}")

    for col, (kind, required) in schema.items():
        series = df[col]
        if not _KIND_CHECK[kind](series):
            raise SchemaError(f"[{schema_name}] 列 {col!r} 类型不符：期望 {kind}，实际 {series.dtype}")
        if required and series.isna().any():
            n = int(series.isna().sum())
            raise SchemaError(f"[{schema_name}] 列 {col!r} 存在 {n} 个空值")

    return df


def _read_csv(path: Path, schema_name: str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise SchemaError(f"文件不存在: {path}")
    df = pd.read_csv(path, encoding="utf-8")
    df.columns = [str(c).strip() for c in df.columns]
    return validate_frame(df, schema_name)


def _write_csv(df: pd.DataFrame, path: Path, schema_name: str, *, allow_extra: bool = True) -> None:
    validate_frame(df, schema_name, allow_extra=allow_extra)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


# --------------------------------------------------------------------------
# 时间辅助
# --------------------------------------------------------------------------

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


def parse_utc(text: str) -> _dt.datetime:
    """解析 ISO8601 时间串（容忍结尾的 Z）。"""
    s = str(text).strip().replace("Z", "+00:00")
    if not _ISO_RE.match(str(text).strip()):
        raise SchemaError(f"非法 ISO8601 时间: {text!r}")
    dt = _dt.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt


def to_utc_str(dt: _dt.datetime) -> str:
    """统一输出成 ``....Z`` 形式，保证四人的表可直接字符串比对。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def t0() -> _dt.datetime:
    return parse_utc(config.PLAN_T0_UTC)


def offset_to_utc(t_offset_s: float) -> str:
    """相对 t0 的秒 -> ISO8601 UTC 字符串。"""
    return to_utc_str(t0() + _dt.timedelta(seconds=float(t_offset_s)))


# --------------------------------------------------------------------------
# 原始数据读取（楼心荡区依赖）
# --------------------------------------------------------------------------


def read_stations_raw(path: Path | None = None) -> pd.DataFrame:
    """读 ``站址.txt``。

    原始格式（UTF-8）::

        站址：经度(度)，纬度(度)，海拔(m）
        1：-3.609548, 25.473033,273
        ...
        设备观测限制：最低仰角不低于10度，最高不超过85度
    """
    path = Path(path or config.RAW_STATION_FILE)
    if not path.exists():
        raise SchemaError(f"文件不存在: {path}")

    rows: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("站址：") or line.startswith("设备观测限制"):
            continue
        m = re.match(r"^(\d+)\s*[:：]\s*(.+)$", line)
        if not m:
            continue
        station_id = int(m.group(1))
        parts = [p.strip() for p in m.group(2).split(",")]
        if len(parts) < 3:
            raise SchemaError(f"站址行字段不足: {line!r}")
        rows.append(
            {
                "station_id": station_id,
                "lon_deg": float(parts[0]),
                "lat_deg": float(parts[1]),
                "alt_m": float(parts[2]),
                "min_elev_deg": config.MIN_ELEV_DEG,
                "max_elev_deg": config.MAX_ELEV_DEG,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise SchemaError(f"未解析到任何站址: {path}")
    return validate_frame(df, "stations")


def read_tle_raw(path: Path | None = None) -> pd.DataFrame:
    """读 ``轨道.txt``（两行式 TLE，带 ``0 NAME`` 名称行）。

    返回列：``sat_id`` / ``satnum_raw`` / ``name`` / ``line1`` / ``line2``。
    ``sat_id`` 已经过 Alpha-5 解码。
    """
    path = Path(path or config.RAW_TLE_FILE)
    if not path.exists():
        raise SchemaError(f"文件不存在: {path}")

    lines = [l.rstrip("\n") for l in path.read_text(encoding="utf-8").splitlines()]
    records: list[dict[str, object]] = []
    pending_name: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("0 "):
            pending_name = line[2:].strip()
            i += 1
            continue
        if line.startswith("1 "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith("2 "):
                raise SchemaError(f"第 {i + 1} 行的一号行缺少配套二号行")
            line1 = lines[i].strip()
            line2 = lines[i + 1].strip()
            token = line1[2:7].strip()
            records.append(
                {
                    "sat_id": decode_satnum(token),
                    "satnum_raw": token,
                    "name": pending_name if pending_name is not None else "",
                    "line1": line1,
                    "line2": line2,
                }
            )
            pending_name = None
            i += 2
            continue
        i += 1

    df = pd.DataFrame.from_records(records)
    if df.empty:
        raise SchemaError(f"未解析到任何 TLE: {path}")
    if df["sat_id"].duplicated().any():
        dup = df.loc[df["sat_id"].duplicated(), "sat_id"].tolist()
        raise SchemaError(f"TLE 编号重复: {dup[:10]}")
    return df


def read_priority_raw(path: Path | None = None) -> dict[str, list[int]]:
    """读三份优先级目标表，返回 ``{"high": [...], "mid": [...], "low": [...]}``。

    原始文件是单行逗号分隔的整数编号（每行一条也在容忍范围内）。
    """
    out: dict[str, list[int]] = {}
    for level, fp in config.RAW_PRIORITY_FILES.items():
        path_p = Path(path) if path is not None else fp
        if path_p is None or not path_p.exists():
            raise SchemaError(f"文件不存在: {path_p}")
        text = path_p.read_text(encoding="utf-8")
        ids: list[int] = []
        for token in text.replace("\r", "\n").replace(",", "\n").split("\n"):
            token = token.strip()
            if not token:
                continue
            if not token.lstrip("+-").isdigit():
                raise SchemaError(f"[{level}] 非法编号: {token!r}")
            ids.append(int(token))
        if len(set(ids)) != len(ids):
            raise SchemaError(f"[{level}] 存在重复编号")
        out[level] = ids
    return out


def build_sat_meta(tle_df: pd.DataFrame, priority_map: dict[str, list[int]]) -> pd.DataFrame:
    """把 TLE 与三份优先级表合成 ``sat_meta.csv``，并在不一致时抛错。

    这是"数据自检"的关键一步：历史上曾因 Alpha-5 未解码导致 108 颗星丢失。
    """
    id_to_level: dict[int, str] = {}
    for level, ids in priority_map.items():
        for sid in ids:
            if sid in id_to_level:
                raise SchemaError(f"编号 {sid} 同时出现在 {id_to_level[sid]} 与 {level}")
            id_to_level[sid] = level

    missing = sorted(id_to_level.keys() - set(tle_df["sat_id"].tolist()))
    if missing:
        raise SchemaError(f"有 {len(missing)} 个优先级编号在 TLE 中不存在: {missing[:10]}")
    unrated = sorted(set(tle_df["sat_id"].tolist()) - id_to_level.keys())
    if unrated:
        raise SchemaError(f"有 {len(unrated)} 颗 TLE 卫星没有优先级: {unrated[:10]}")

    meta = pd.DataFrame(
        {
            "sat_id": tle_df["sat_id"].astype("int64"),
            "name": tle_df["name"].astype("object"),
            "priority": tle_df["sat_id"].map(id_to_level).astype("object"),
            "priority_score": tle_df["sat_id"].map(lambda s: config.PRIORITY_SCORE[id_to_level[s]]).astype("int64"),
            "tle_epoch_utc": tle_df.apply(_epoch_from_tle, axis=1),
        }
    )
    return validate_frame(meta, "sat_meta")


def _epoch_from_tle(row: pd.Series) -> str:
    """从 TLE 一号行解析历元（YYDDD.DDDDDDDD）。"""
    raw = str(row["line1"])
    token = raw[18:32].strip()
    if not token:
        raise SchemaError(f"TLE 缺少历元字段: {raw!r}")
    yy = int(token[:2])
    year = 2000 + yy if yy < 57 else 1900 + yy
    doy = float(token[2:])
    dt = _dt.datetime(year, 1, 1, tzinfo=_dt.timezone.utc) + _dt.timedelta(days=doy - 1.0)
    return to_utc_str(dt)


# --------------------------------------------------------------------------
# 契约文件的读写入口
# --------------------------------------------------------------------------


def load_stations(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or config.STATIONS_CSV, "stations")


def save_stations(df: pd.DataFrame, path: Path | None = None) -> None:
    _write_csv(df, path or config.STATIONS_CSV, "stations")


def load_sat_meta(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or config.SAT_META_CSV, "sat_meta")


def save_sat_meta(df: pd.DataFrame, path: Path | None = None) -> None:
    _write_csv(df, path or config.SAT_META_CSV, "sat_meta")


def load_windows(path: Path | None = None) -> pd.DataFrame:
    """读窗口表。全队统一走这个入口——它是唯一的数据源。"""
    return _read_csv(path or config.WINDOWS_CSV, "windows")


def save_windows(df: pd.DataFrame, path: Path | None = None) -> None:
    _write_csv(df, path or config.WINDOWS_CSV, "windows")


def load_plan(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or config.PLAN_CSV, "plan")


def save_plan(df: pd.DataFrame, path: Path | None = None) -> None:
    """写计划表。落盘前会做一轮契约校验，但不做业务可行性校验（那是 rules 的职责）。"""
    _write_csv(df, path or config.PLAN_CSV, "plan")


def iter_rows(df: pd.DataFrame) -> Iterable[dict[str, object]]:
    """按行产出普通 dict，避免各模块各自 ``iterrows`` 造成 dtype 漂移。"""
    for row in df.to_dict(orient="records"):
        yield row


def csv_fieldnames(path: Path) -> list[str]:
    """读表头，供自检脚本比对。"""
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))
