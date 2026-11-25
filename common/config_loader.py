"""Validate and snapshot configuration before any browser mutation."""
from pathlib import Path
import openpyxl
from common.config_schema import validate_headers, is_supported_image, RENAME_HEADER


def read_config(path, *, options=(False, False, False, False), preset=False, rename_option=False, allow_blank_content=False):
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != '.xlsx':
        raise ValueError('请先选择有效的 .xlsx 配置文件')
    if len(options) != 4:
        raise ValueError('执行内容无效')
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        headers = [cell.value for cell in sheet[1]]
        if not validate_headers(headers, allow_text=True):
            raise ValueError('配置文件应包含：选项名（或选项值名称）、PC选项值、移动选项值、PC图路径、移动图路径')
        if rename_option and headers[5:6] != [RENAME_HEADER]:
            raise ValueError("修改选项名需要在配置中填写第 6 列「新选项名」")
        rows = []
        for number, row in enumerate(sheet.iter_rows(min_row=2, max_col=6 if rename_option else 5, values_only=True), 2):
            if all(value is None or str(value).strip() == '' for value in row):
                continue
            values = ['' if value is None else str(value).strip() for value in row]
            required = [0]
            if not preset and not allow_blank_content:
                required.extend(column for flag, column in zip(options, (3, 1, 4, 2)) if flag)
            if rename_option:
                required.append(5)
            for column in required:
                if not values[column]:
                    raise ValueError(f'配置文件第 {number} 行第 {column+1} 列不能为空')
            if not preset:
                for selected, column in ((options[0],3),(options[2],4)):
                    if selected and values[column]:
                        image = Path(values[column]).expanduser()
                        if not image.is_absolute():
                            image = source.parent / image
                        if not image.is_file() or not is_supported_image(image):
                            raise ValueError(f'配置文件第 {number} 行图片不存在或格式不支持：{values[column]}')
                        values[column] = str(image.resolve())
            rows.append((number, tuple(values)))
        if not rows:
            raise ValueError('配置文件没有可执行的数据')
        return rows
    finally:
        workbook.close()
