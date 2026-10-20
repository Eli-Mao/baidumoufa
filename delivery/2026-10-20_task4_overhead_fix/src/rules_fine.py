"""细粒度物理判定与放置规则（共享内核）。

本模块被 make_patch.py 与 verify_patch.py 共用，保证"生成补丁"和"复核补丁"
用的是同一套物理口径——避免出现"生成时通过、复核时不通过"的假阳性。

物理口径（与 Iceswing 项目 config/competition_rules.json 一致）：
    1. 站点仰角 ∈ [10°, 85°]；
    2. 测站太阳高度角 < -6°；
    3. 卫星本身受太阳照亮；
    4. 观测时长 ∈ [120, 240] s，时长系数在 120s→0.60、240s→1.00 之间线性；
    5. 同站相邻任务间隔 ≥ 30 s；
    6. 同一目标距上次观测结束 ≥ 48 h 才能再观测。

注意：第 1 条的上限 85° 是"过顶盲区"的来源。真实仰角在过顶瞬间会冲到 85° 以上，
必须把连续可见区间在该点切分成两段，否则会生成"中间必然越界"的任务。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# 赛题口径常量（与 Iceswing 项目 config/competition_rules.json 对齐）
# --------------------------------------------------------------------------
MIN_ELEV_DEG = 10.0
MAX_ELEV_DEG = 85.0
SUN_ELEV_MAX_DEG = -6.0

MIN_DUR_S = 120.0
MAX_DUR_S = 240.0
DUR_SCORE_AT_MIN = 0.60
DUR_SCORE_AT_MAX = 1.00

SWITCH_S = 30.0
REPEAT_COOLDOWN_S = 48.0 * 3600.0

PRIORITY_SCORE = {"high": 5.0, "medium": 3.0, "mid": 3.0, "low": 2.0}

UTC = timezone.utc


# --------------------------------------------------------------------------
# 基础换算
# --------------------------------------------------------------------------


def parse_utc(text: str) -> datetime:
    """解析 ``YYYY-MM-DD HH:MM:SS`` / ISO8601（带或不带 Z），统一为 UTC aware。"""
    s = str(text).strip().replace("Z", "+00:00").replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def duration_score(dur_s: float) -> float:
    """观测时长 -> 时长得分系数（120s→0.60，240s→1.00，线性）。"""
    d = float(dur_s)
    if d < MIN_DUR_S - 1e-9 or d > MAX_DUR_S + 1e-9:
        return 0.0
    if d >= MAX_DUR_S:
        return DUR_SCORE_AT_MAX
    span = MAX_DUR_S - MIN_DUR_S
    ratio = (d - MIN_DUR_S) / span
    return DUR_SCORE_AT_MIN + (DUR_SCORE_AT_MAX - DUR_SCORE_AT_MIN) * ratio


def task_score(priority: str, dur_s: float) -> float:
    return PRIORITY_SCORE[str(priority).strip().lower()] * duration_score(dur_s)


# --------------------------------------------------------------------------
# 站点读取
# --------------------------------------------------------------------------

_STATION_RE = re.compile(r"^(\d+)\s*[:：]\s*(.+)$")


def read_stations(path: str | Path) -> dict[int, tuple[float, float, float]]:
    """读 ``stations.txt``，返回 ``{station_id: (lon_deg, lat_deg, alt_m)}``。

    原始经度可能是 0~360 惯例（如 249.1、290.5），这里统一折算到 -180~180。
    """
    rows: dict[int, tuple[float, float, float]] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip().lstrip("\ufeff")
        m = _STATION_RE.match(line)
        if not m:
            continue
        parts = [p.strip() for p in m.group(2).split(",")]
        if len(parts) < 3:
            continue
        lon, lat, alt = float(parts[0]), float(parts[1]), float(parts[2])
        if lon > 180.0:
            lon -= 360.0
        rows[int(m.group(1))] = (lon, lat, alt)
    return rows


# --------------------------------------------------------------------------
# TLE 读取（含 Alpha-5 解码）
# --------------------------------------------------------------------------

_ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def decode_satnum(token: str) -> int:
    t = token.strip()
    if t.isdigit():
        return int(t)
    head, body = t[0].upper(), t[1:]
    if head not in _ALPHA5 or len(t) != 5 or not body.isdigit():
        raise ValueError(f"非法 TLE 编号: {token!r}")
    return (_ALPHA5.index(head) + 10) * 10000 + int(body)


def load_tles(path: str | Path, wanted: set[int]) -> dict[int, tuple[str, str]]:
    """从三行式 TLE 文件里挑出指定编号，返回 ``{sat_id: (line1, line2)}``。"""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    out: dict[int, tuple[str, str]] = {}
    i = 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            try:
                sid = decode_satnum(lines[i][2:7])
            except ValueError:
                sid = None
            if sid in wanted:
                out[sid] = (lines[i].strip(), lines[i + 1].strip())
            i += 2
        else:
            i += 1
    return out


# --------------------------------------------------------------------------
# 连续合法区间
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """一段连续满足全部可见性条件的区间（秒级精度，边界已细化）。"""

    start: datetime
    end: datetime

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()


def mask_to_segments(times: list[datetime], ok: list[bool]) -> list[tuple[datetime, datetime]]:
    """把逐点布尔掩码合并成连续区间（纯函数，便于离线测试）。"""
    segs: list[tuple[datetime, datetime]] = []
    cur = None
    for t, good in zip(times, ok):
        if good:
            cur = (t, t) if cur is None else (cur[0], t)
        elif cur is not None:
            segs.append(cur)
            cur = None
    if cur is not None:
        segs.append(cur)
    return segs


def place_in_segment(
    seg: tuple[datetime, datetime],
    *,
    busy: list[tuple[datetime, datetime]],
    guard_s: float = 1.0,
    step_s: float = 5.0,
    desired: float = MAX_DUR_S,
) -> tuple[datetime, datetime, float] | None:
    """在一段合法区间内放一条任务，返回 ``(start, end, dur_s)``；放不下返回 None。

    规则：两端各留 ``guard_s`` 边距；尽量长（上限 ``desired``，且不超过 240 s）；
    与同站其它任务之间前后各留 ``SWITCH_S`` 切换时间；最短不得少于 120 s。
    """
    lo = seg[0] + timedelta(seconds=guard_s)
    hi = seg[1] - timedelta(seconds=guard_s)
    if (hi - lo).total_seconds() < MIN_DUR_S:
        return None

    cur = lo
    while True:
        room = (hi - cur).total_seconds()
        if room < MIN_DUR_S:
            return None
        dur = min(desired, MAX_DUR_S, room)
        cand_s, cand_e = cur, cur + timedelta(seconds=dur)
        conflict = False
        for bs, be in busy:
            if cand_s < be + timedelta(seconds=SWITCH_S) and cand_e + timedelta(seconds=SWITCH_S) > bs:
                conflict = True
                cur = be + timedelta(seconds=SWITCH_S)
                break
        if not conflict:
            return cand_s, cand_e, dur
        if cur > hi:
            return None


def station_busy(plan_rows: list[dict], station_id: int, exclude_index: int | None = None):
    """取出某站的其它任务占用区间（用于切换冲突判定）。"""
    out = []
    for i, r in enumerate(plan_rows):
        if i == exclude_index:
            continue
        if int(r["station_id"]) != int(station_id):
            continue
        out.append((parse_utc(r["start_utc"]), parse_utc(r["end_utc"])))
    return sorted(out)


def cooldown_ok(
    plan_rows: list[dict],
    target_id: int,
    new_start: datetime,
    new_end: datetime,
    exclude_index: int | None = None,
) -> bool:
    """同一目标与前后各次观测之间，间隔是否满足 48 小时冷却。"""
    for i, r in enumerate(plan_rows):
        if i == exclude_index:
            continue
        if int(r["target_id"]) != int(target_id):
            continue
        s, e = parse_utc(r["start_utc"]), parse_utc(r["end_utc"])
        if new_start >= e:
            gap = (new_start - e).total_seconds()
        elif new_end <= s:
            gap = (s - new_end).total_seconds()
        else:
            return False  # 时间重叠，必然违规
        if gap < REPEAT_COOLDOWN_S - 1e-9:
            return False
    return True


# --------------------------------------------------------------------------
# 其它
# --------------------------------------------------------------------------


def haversine_free_checks() -> None:
    """占位：本项目不需要大圆距离，保留函数仅为避免误用 math 未导入。"""
    _ = math.pi
