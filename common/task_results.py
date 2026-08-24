"""Shared task statistics and result formatting."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class TaskReport:
    total: int
    succeeded: int
    failed: int
    duration_seconds: float
    success_details: List[str] = field(default_factory=list)
    failure_details: List[str] = field(default_factory=list)

    @property
    def success(self):
        return self.failed == 0


def format_task_report(report, *, detail_limit=10):
    minutes = int(report.duration_seconds // 60)
    seconds = report.duration_seconds % 60
    lines = [
        "任务执行完成！",
        "",
        f"总任务数：{report.total}",
        f"完成任务数：{report.succeeded}",
        f"失败任务数：{report.failed}",
        f"任务运行时间：{minutes}分{seconds:.2f}秒",
    ]
    for title, details in (("成功的任务", report.success_details), ("失败的任务", report.failure_details)):
        if not details:
            continue
        lines.extend(("", f"{title}："))
        lines.extend(details[:detail_limit])
        if len(details) > detail_limit:
            lines.append(f"...（还有 {len(details) - detail_limit} 条记录）")
    return "\n".join(lines)
