"""赛题四：万级空间目标多站观测任务规划。

分区（所有权见 README.md「分区与所有权」）：
    契约层 / 总控   川谷   ：config.py, io_schema.py, pipeline.py, optimize.py, report.py
    轨道与窗口      楼心荡 ：propagate.py, windows.py
    调度算法        Iceswing：scheduler.py
    评分与约束      Priime ：rules.py, scoring.py

任何跨区调用只允许走本 __init__ 暴露的公共入口。
"""

__version__ = "0.1.0"

__all__ = ["config", "io_schema", "rules"]
