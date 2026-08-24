"""Shared Excel generator used by Deedraw and PIM."""

from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill

from common.config_schema import config_row, is_supported_image


def generate_config_workbook(image_dir, output_path, headers, recursive=False, add_prefix=False):
    image_dir = Path(image_dir)
    output_path = Path(output_path)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "File Names"
    sheet.append(list(headers))
    for index, width in enumerate((20, 20, 20, 50, 50), start=1):
        sheet.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width
    fill = PatternFill(start_color="FFFAA500", end_color="FFFAA500", fill_type="solid")
    for cell in sheet[1]:
        cell.fill = fill

    candidates = image_dir.rglob("*") if recursive else image_dir.iterdir()
    invalid_files = []
    image_count = 0
    for path in sorted(candidates):
        if not path.is_file():
            continue
        if not is_supported_image(path):
            invalid_files.append(str(path))
            continue
        option_name = path.stem
        if add_prefix:
            relative_parent = path.parent.relative_to(image_dir)
            if relative_parent.parts:
                option_name = "-".join(relative_parent.parts) + "-" + option_name
        sheet.append(config_row(path, option_name))
        image_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    workbook.close()
    return {"path": str(output_path), "image_count": image_count, "invalid_files": invalid_files}
