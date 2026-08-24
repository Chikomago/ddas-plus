import unittest

from pathlib import Path
from tempfile import TemporaryDirectory

from common.config_schema import config_row, is_supported_image, validate_headers
from common.config_generator import generate_config_workbook
from common.config_schema import DEEDRAW_HEADERS, PIM_HEADERS
import openpyxl


class ConfigFormatTests(unittest.TestCase):
    def test_accepts_deedraw_header(self):
        self.assertTrue(validate_headers([
            "选项值名称（表头不要删）", "PC选项值", "移动选项值", "PC图路径", "移动图路径"
        ]))

    def test_accepts_pim_header(self):
        self.assertTrue(validate_headers([
            "选项名", "PC选项值", "移动选项值", "PC图路径", "移动图路径"
        ]))

    def test_rejects_wrong_column_order(self):
        self.assertFalse(validate_headers([
            "选项名", "移动选项值", "PC选项值", "PC图路径", "移动图路径"
        ]))

    def test_rejects_incomplete_header(self):
        self.assertFalse(validate_headers(["选项名", "PC选项值"]))

    def test_image_extensions_are_case_insensitive(self):
        self.assertTrue(is_supported_image("example.PNG"))
        self.assertFalse(is_supported_image("example.txt"))

    def test_shared_row_uses_absolute_path(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "蓝色.jpg"
            row = config_row(image)
            self.assertEqual(row[:3], ["蓝色", "蓝色", "蓝色"])
            self.assertEqual(row[3], str(image.resolve()))
            self.assertEqual(row[3], row[4])

    def test_generator_supports_pim_non_recursive_mode(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "主图.jpg").touch()
            nested = root / "分类"
            nested.mkdir()
            (nested / "子图.png").touch()
            output = root / "pim.xlsx"
            result = generate_config_workbook(root, output, PIM_HEADERS)
            self.assertEqual(result["image_count"], 1)
            workbook = openpyxl.load_workbook(output, read_only=True)
            self.assertEqual(workbook.active.max_row, 2)
            workbook.close()

    def test_generator_supports_deedraw_recursive_prefix(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "一级" / "二级"
            nested.mkdir(parents=True)
            (nested / "蓝色.png").touch()
            output = root / "deedraw.xlsx"
            result = generate_config_workbook(root, output, DEEDRAW_HEADERS, recursive=True, add_prefix=True)
            self.assertEqual(result["image_count"], 1)
            workbook = openpyxl.load_workbook(output, read_only=True)
            self.assertEqual(workbook.active.cell(2, 1).value, "一级-二级-蓝色")
            workbook.close()


if __name__ == "__main__":
    unittest.main()
