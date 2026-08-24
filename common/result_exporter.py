"""Shared Excel export for task results."""

import os
from datetime import datetime

import openpyxl
import openpyxl.styles as styles


def export_task_results(settings, total, succeeded, failed, success_rows, failure_rows,
                        minutes=None, seconds=None):
    result_dir = settings.get("task_result_path", os.getcwd())
    os.makedirs(result_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(result_dir, f"任务结果_{timestamp}.xlsx")

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "执行结果"
    headers = ["执行结果", "字段编码", "行号", "选项值"]
    for column, header in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=column, value=header)
        cell.fill = styles.PatternFill(start_color="FFFAA500", end_color="FFFAA500", fill_type="solid")
        cell.font = styles.Font(bold=True)
    for column, width in zip("ABCD", (15, 20, 10, 40)):
        sheet.column_dimensions[column].width = width

    row_number = 2
    for label, rows, color in (("成功", success_rows, "90EE90"), ("失败", failure_rows, "FFB6C1")):
        fill = styles.PatternFill(start_color=color, end_color=color, fill_type="solid")
        for field_code, source_row, value in rows:
            for column, cell_value in enumerate((label, field_code, source_row, value), 1):
                sheet.cell(row=row_number, column=column, value=cell_value).fill = fill
            row_number += 1

    summary = workbook.create_sheet(title="统计信息")
    summary.append(["统计项", "数值"])
    summary["A1"].font = summary["B1"].font = styles.Font(bold=True)
    rate = f"{(succeeded / total * 100):.2f}%" if total else "0%"
    rows = [("总任务数", total), ("完成任务数", succeeded), ("失败任务数", failed), ("成功率", rate)]
    if minutes is not None and seconds is not None:
        rows.append(("执行时间", f"{minutes}分{seconds:.2f}秒"))
    for item in rows:
        summary.append(item)

    field_stats = {}
    for field_code, _, _ in success_rows:
        field_stats.setdefault(field_code, [0, 0])[0] += 1
    for field_code, _, _ in failure_rows:
        field_stats.setdefault(field_code, [0, 0])[1] += 1
    summary.append([])
    summary.append(["各字段统计", "成功/失败"])
    for field_code, (ok, bad) in field_stats.items():
        summary.append([field_code, f"{ok}/{bad}"])

    workbook.save(file_path)
    workbook.close()
    return file_path
