import os
from tkinter import messagebox
from datetime import datetime
import logging
from common.config_schema import DEEDRAW_HEADERS
from common.config_generator import generate_config_workbook
from common.file_dialogs import choose_directory, choose_excel_file, choose_browser, open_file, get_browser_version
import tkinter as tk

class DeedrawConfigAdapter:
    def __init__(self, settings=None):
        """初始化文件处理器

        Args:
            settings: Settings实例，用于获取配置信息
        """
        self.settings = settings
        self.root = None  # 将在GUI中设置

    def select_directory(self, entry_widget, title="选择目录"):
        directory = choose_directory(title)
        if directory:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, directory)

    def generate_excel_from_directory(self, folder_path, code_entry, field_rows, file_status_label):
        """从目录生成Excel文件"""
        try:
            if not folder_path:
                return

            # 获取当前时间
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 使用设置中的任务结果导出路径
            result_dir = self.settings.get('config_path', os.getcwd())
            folder_name = os.path.basename(folder_path)
            file_path = os.path.join(result_dir, f"{folder_name}_{timestamp}_data.xlsx")

            # 检查是否有子文件夹
            has_subfolders = any(os.path.isdir(os.path.join(folder_path, f)) for f in os.listdir(folder_path))

            # 询问是否添加文件夹名作为前缀（仅在有子文件夹时询问）
            add_prefix = False
            if has_subfolders:
                result = messagebox.askquestion("提示", "是否将每一级子文件夹的名称添加到选项值名称前缀？")
                add_prefix = result == 'yes'

            result = generate_config_workbook(
                folder_path,
                file_path,
                DEEDRAW_HEADERS,
                recursive=True,
                add_prefix=add_prefix,
            )
            if result['invalid_files']:
                logging.info("已跳过 %s 个非图片文件", len(result['invalid_files']))

            # 更新字段行信息
            for i, row_info in enumerate(field_rows):
                if row_info['field_entry'] == code_entry:
                    row_info['file_path'] = file_path
                    file_status_label.config(text="✓", foreground="green")
                    logging.info(f"第 {i+1} 行Excel文件已生成: {file_path}")
                    break
            else:
                logging.error("未找到对应的字段行信息")
                messagebox.showerror("错误", "未找到对应的字段行信息")

        except Exception as e:
            logging.error(f"生成 Excel 文件时出错: {str(e)}")
            messagebox.showerror("错误", f"生成 Excel 文件时出错: {str(e)}")

    def browse_file(self):
        file_path = choose_excel_file()
        if file_path:
            self.file_path = file_path
        return file_path or None

    def browse_file_for_row(self, file_status_label, code_entry, field_rows):
        file_path = choose_excel_file()
        if not file_path:
            return
        file_status_label.config(text="✓", foreground="green")
        for row_info in field_rows:
            if row_info['field_entry'] == code_entry:
                row_info['file_path'] = file_path
                return
        messagebox.showerror("错误", "未找到对应的字段行信息")

    def view_file_for_row(self, code_entry, field_rows):
        for row_info in field_rows:
            if row_info['field_entry'] == code_entry:
                try:
                    open_file(row_info.get('file_path', ''))
                except Exception as error:
                    messagebox.showerror("错误", str(error))
                return
        messagebox.showerror("错误", "未找到对应的字段行信息")

    def select_browser(self, entry_widget, version_label=None, title="选择Chrome浏览器"):
        path = choose_browser(title)
        if not path:
            return None
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, path)
        if version_label:
            try:
                version_label['text'] = get_browser_version(path)
            except Exception as error:
                logging.error("获取浏览器版本失败: %s", error)
                version_label['text'] = "版本获取失败"
        return path
