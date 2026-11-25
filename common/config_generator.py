"""Shared Excel generator used by Deedraw and PIM."""

from collections import defaultdict, deque
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill

from common.config_schema import config_row, is_supported_image


def scan_images(sources, recursive, add_prefix, include_source_name, invalid_files):
    for source in map(Path, sources):
        if source.is_dir():
            candidates = sorted(source.rglob("*") if recursive else source.iterdir())
        else:
            candidates = [source]
        for path in candidates:
            if not path.is_file():
                continue
            if not is_supported_image(path):
                invalid_files.append(str(path))
                continue
            name = path.stem
            if add_prefix and source.is_dir():
                parts = path.parent.relative_to(source).parts
                if include_source_name and source.name:
                    parts = (source.name, *parts)
                name = "-".join((*parts, name))
            elif add_prefix and include_source_name and path.parent.name:
                name = f"{path.parent.name}-{name}"
            yield path, name


def paired_rows(pc_images, mobile_images, pairs=None):
    rows = []
    empty_mobile_cells = defaultdict(deque)
    for path, name in pc_images:
        row = [name, path.stem, "", str(path.resolve()), ""]
        rows.append(row)
        if pairs is None:
            empty_mobile_cells[path.stem].append(row)

    if pairs is not None:
        mobile_images = list(mobile_images)
        if (len(pairs) != len(mobile_images) or
                any(index is not None and (type(index) is not int or not 0 <= index < len(rows)) for index in pairs) or
                len({index for index in pairs if index is not None}) != sum(index is not None for index in pairs)):
            raise ValueError("图片配对无效")
    for mobile_index, (path, name) in enumerate(mobile_images):
        if pairs is None:
            available = empty_mobile_cells[path.stem]
            row = available.popleft() if available else None
        else:
            pc_index = pairs[mobile_index]
            row = rows[pc_index] if pc_index is not None else None
        if row is not None:
            row[2] = path.stem
            row[4] = str(path.resolve())
        else:
            rows.append([name, "", path.stem, "", str(path.resolve())])
    return rows


def generate_config_workbook(image_dir, output_path, headers, recursive=False, add_prefix=False,
                             *, additional_dirs=(), include_source_name=False, mobile_sources=None):
    sources = [image_dir, *additional_dirs] if image_dir is not None else list(additional_dirs)
    output_path = Path(output_path)
    invalid_files = []
    images = scan_images(sources, recursive, add_prefix, include_source_name, invalid_files)
    if mobile_sources is None:
        rows = (config_row(path, name) for path, name in images)
    else:
        mobile_images = scan_images(mobile_sources, recursive, add_prefix, include_source_name, invalid_files)
        rows = paired_rows(images, mobile_images)

    image_count = write_config_rows(output_path, headers, rows)
    return {"path": str(output_path), "image_count": image_count, "invalid_files": invalid_files}


def write_config_rows(output_path, headers, rows):
    workbook = openpyxl.Workbook()
    try:
        sheet = workbook.active
        sheet.title = "File Names"
        sheet.append(list(headers))
        for index, width in enumerate((20, 20, 20, 50, 50)[:len(headers)], start=1):
            sheet.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width
        fill = PatternFill(start_color="FFFAA500", end_color="FFFAA500", fill_type="solid")
        for cell in sheet[1]:
            cell.fill = fill

        image_count = 0
        for row in rows:
            sheet.append(row)
            for cell in sheet[image_count + 2]:
                if cell.data_type == "f":
                    cell.data_type = "s"
            image_count += 1

        output_path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(output_path)
        return image_count
    finally:
        workbook.close()
