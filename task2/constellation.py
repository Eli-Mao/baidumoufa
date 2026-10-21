"""统一历元。构型生成见 designs.py，优化见 optimizer.py。"""
from datetime import datetime

from sso import jd_from_datetime


def epoch_jd(year=2027, month=1, day=1):
    """仿真起点 / 轨道根数历元 2027-01-01 00:00:00 UTCG 的儒略日。"""
    return jd_from_datetime(datetime(year, month, day))
