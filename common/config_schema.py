"""Shared Excel configuration schema for DDAS and PIM."""

from pathlib import Path


RENAME_HEADER = "新选项名"
VALUE_HEADERS = ["PC选项值", "移动选项值", "PC图路径", "移动图路径"]
DEEDRAW_HEADERS = ["选项值名称（表头不要删）", *VALUE_HEADERS]
PIM_HEADERS = ["选项名", *VALUE_HEADERS]
FIRST_HEADER_ALIASES = {"选项名", "选项值名称", "选项值名称（表头不要删）"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}


def validate_headers(headers, *, allow_text=False):
    """Return whether headers match the shared five-column contract."""
    if allow_text and len(headers) == 3:
        return headers[0] in FIRST_HEADER_ALIASES and list(headers[1:]) == VALUE_HEADERS[:2]
    return (
        len(headers) >= 5
        and headers[0] in FIRST_HEADER_ALIASES
        and list(headers[1:5]) == VALUE_HEADERS
    )


def is_supported_image(path):
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def config_row(image_path, option_name=None):
    """Create one shared five-column row from an image path."""
    path = Path(image_path)
    name = option_name if option_name is not None else path.stem
    absolute_path = str(path.resolve())
    return [name, name, name, absolute_path, absolute_path]
