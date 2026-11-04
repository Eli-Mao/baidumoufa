"""Attach full scheduled-task audit results to a benchmark report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--repair", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.outdir / "profile_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    repair = json.loads(args.repair.read_text(encoding="utf-8"))
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    violations = repair.get("violations", [])
    accepted = bool(audit.get("all_pass") and not violations)
    report["status"] = "completed" if accepted else "failed_full_task_audit"
    report["final_plan"] = {
        "path": str(args.repair.with_suffix(".csv")),
        "task_count": int(repair.get("tasks", 0)),
        "score": repair.get("score"),
        "scheduler_violation_count": len(violations),
        "scheduler_violations": violations,
        "dropped_unrepairable_tasks": repair.get("dropped_unrepairable_tasks", []),
        "physical_audit": audit,
        "continuous_validity_proven": False,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "tasks": report["final_plan"]["task_count"],
                      "scheduler_violations": len(violations),
                      "physical_audit": audit.get("all_pass")}, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
