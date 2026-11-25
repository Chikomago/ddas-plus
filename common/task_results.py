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

    skipped_details: List[str] = field(default_factory=list)
    modified_details: List[str] = field(default_factory=list)
    overwritten_details: List[str] = field(default_factory=list)

    @property
    def pending(self):
        return max(0, self.total-self.succeeded-self.failed-len(self.skipped_details))

    @property
    def success(self):
        return self.total > 0 and self.failed == 0 and self.succeeded + len(self.skipped_details) == self.total


def format_task_report(report, *, detail_limit=10):
    minutes = int(report.duration_seconds // 60)
    seconds = report.duration_seconds % 60
    lines = [
        "任务执行成功！" if report.success else "任务执行完成，存在失败或未完成项目。",
        "",
        f"总任务数：{report.total}",
        f"完成任务数：{report.succeeded}",
        f"失败任务数：{report.failed}",
        f"任务运行时间：{minutes}分{seconds:.2f}秒",
    ]
    pending = report.pending
    if report.skipped_details:
        lines.append(f"跳过任务数：{len(report.skipped_details)}")
    if report.modified_details:
        lines.append(f"修改任务数：{len(report.modified_details)}")
    if report.overwritten_details:
        lines.append(f"覆盖任务数：{len(report.overwritten_details)}")
    if pending:
        lines.append(f"未完成任务数：{pending}")
    modified = set(report.modified_details)
    other_successes = [detail for detail in report.success_details if detail not in modified]
    for title, details in (("成功的任务", other_successes), ("失败的任务", report.failure_details),
                           ("跳过的任务", report.skipped_details), ("已覆盖的任务", report.overwritten_details), ("已修改的任务", report.modified_details)):
        if not details:
            continue
        lines.extend(("", f"{title}："))
        lines.extend(details[:detail_limit])
        if len(details) > detail_limit:
            lines.append(f"...（还有 {len(details) - detail_limit} 条记录）")
    return "\n".join(lines)


def report_result(report, *, cancelled=False):
    from common.task_models import TaskResult
    message = format_task_report(report)
    if cancelled:
        message = "任务已终止。" + message[message.index("\n"): ]
    return TaskResult(report.success and not cancelled, message, {
        "total": report.total, "succeeded": report.succeeded, "failed": report.failed,
        "pending": report.pending,
        "skipped": len(report.skipped_details), "overwritten": len(report.overwritten_details),
        "modified": len(report.modified_details), "modified_details": list(report.modified_details),
        "skipped_details": list(report.skipped_details), "overwritten_details": list(report.overwritten_details),
        "cancelled": cancelled, "success_details": list(report.success_details),
        "failure_details": list(report.failure_details),
    })


def publish_result(callbacks, result):
    """All tasks emit exactly one terminal notification, also for legacy UI."""
    if result.details.get("cancelled"):
        status, notify = "已终止", callbacks.warning or callbacks.log
    elif result.success:
        status, notify = "已完成", callbacks.info or callbacks.log
    elif result.details.get("succeeded", 0) or result.details.get("skipped", 0):
        status, notify = "部分失败", callbacks.warning or callbacks.error
    else:
        status, notify = "执行失败", callbacks.error
    callbacks.status(status)
    notify(result.message)
    return result
