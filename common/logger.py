import logging
import tkinter as tk
import platform
import subprocess
import os
import datetime
from tkinter import messagebox
from common.log_policy import DiagnosticLogFilter

class TextHandler(logging.Handler):
    """自定义日志处理器，将日志输出到Text小部件"""
    def __init__(self, text_widget, settings):
        super().__init__()
        self.text_widget = text_widget
        self.settings = settings

    def emit(self, record):
        msg = self.format(record)
        def append():
            try:
                self.text_widget.insert(tk.END, msg + '\n')
                self.text_widget.yview(tk.END)
            except tk.TclError:
                pass
        self.text_widget.after(0, append)

    def setup_logging(self):
        """设置日志记录器"""
        logger = logging.getLogger()
        for existing in list(logger.handlers):
            if getattr(existing, "ddas_plus_handler", False):
                logger.removeHandler(existing)
                existing.close()

        self.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.setFormatter(formatter)
        self.filters.clear()
        self.addFilter(DiagnosticLogFilter())
        self.ddas_plus_handler = True

        logger.setLevel(logging.INFO)
        logger.addHandler(self)

        log_dir = self.settings.get('log_export_path', os.getcwd())
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'ddas_plus.log')
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(DiagnosticLogFilter())
        file_handler.ddas_plus_handler = True
        logger.addHandler(file_handler)
        return log_path

    def export_log(self):
        """导出日志到文件"""
        try:
            # 获取当前时间
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # 使用设置中的日志导出路径
            log_dir = self.settings.get('log_export_path', '')
            if not log_dir:
                log_dir = os.getcwd()  # 如果没有设置路径，使用当前目录

            # 确保目录存在
            os.makedirs(log_dir, exist_ok=True)

            # 构建完整的文件路径
            file_path = os.path.join(log_dir, f"log_{timestamp}.txt")

            # 获取日志内容
            log_content = self.text_widget.get("1.0", tk.END)

            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(log_content)

            logging.info(f"日志已导出到: {file_path}")
            messagebox.showinfo("成功", f"日志已导出到:\n{file_path}")


        except Exception as e:
            error_msg = f"导出日志失败: {str(e)}"
            logging.error(error_msg)
            messagebox.showerror("错误", error_msg)

    def clear_log(self):
        """清空日志"""
        try:
            self.text_widget.delete(1.0, tk.END)
        except Exception as e:
            messagebox.showerror("错误", f"清空日志失败: {str(e)}")
