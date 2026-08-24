import logging
import os
import platform
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from common.browser import BrowserInitializer, open_chrome_download


class UnifiedSettingsDialog:
    """One settings dialog shared by Deedraw and PIM."""

    def __init__(self, parent, settings, on_saved=None):
        self.parent = parent
        self.settings = settings
        self.on_saved = on_saved
        self.browser_initializer = BrowserInitializer()
        self.window = tk.Toplevel(parent)
        self.window.title("DDAS PLUS 设置")
        self.window.geometry("680x520")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()
        self._build()

    def _build(self):
        content = ttk.Frame(self.window, padding=14)
        content.pack(fill=tk.BOTH, expand=True)

        paths = tk.LabelFrame(content, text="文件与日志", background='#ECECEC', borderwidth=1, relief=tk.SOLID, highlightthickness=0, padx=10, pady=10)
        paths.pack(fill=tk.X, pady=(0, 10))
        self.log_path = self._path_row(paths, "日志目录", self.settings.settings.get('log_export_path', ''))
        self.result_path = self._path_row(paths, "结果目录", self.settings.settings.get('task_result_path', ''))
        self.config_path = self._path_row(paths, "配置目录", self.settings.settings.get('config_path', ''))

        browser = tk.LabelFrame(content, text="Chrome浏览器设置", background='#ECECEC', borderwidth=1, relief=tk.SOLID, highlightthickness=0, padx=10, pady=10)
        browser.pack(fill=tk.X, pady=(0, 10))
        row = tk.Frame(browser, background='#ECECEC')
        row.pack(fill=tk.X)
        tk.Label(row, text="浏览器路径", width=12, background='#ECECEC').pack(side=tk.LEFT)
        self.chrome_path = ttk.Entry(row)
        self.chrome_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.chrome_path.insert(0, self.settings.settings.get('chrome_path', ''))
        ttk.Button(row, text="浏览", command=self._select_browser).pack(side=tk.LEFT)
        ttk.Button(row, text="测试", command=self._test_browser).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="下载", command=open_chrome_download).pack(side=tk.LEFT, padx=(6, 0))

        behavior = tk.Frame(browser, background='#ECECEC')
        behavior.pack(fill=tk.X, pady=(10, 0))
        self.auto_close = tk.BooleanVar(value=self.settings.settings.get('browser_settings', {}).get('auto_close', False))
        tk.Checkbutton(behavior, text="任务完成后自动关闭浏览器", variable=self.auto_close, background='#ECECEC', activebackground='#ECECEC', highlightthickness=0).pack(side=tk.LEFT)

        pim = tk.LabelFrame(content, text="PIM", background='#ECECEC', borderwidth=1, relief=tk.SOLID, highlightthickness=0, padx=10, pady=10)
        pim.pack(fill=tk.X)
        tk.Label(pim, text="默认像素大小", width=12, background='#ECECEC').pack(side=tk.LEFT)
        self.pixel_size = tk.StringVar(value=self.settings.settings.get('pim_settings', {}).get('pixel_size', '750'))
        tk.Radiobutton(pim, text="750px", value="750", variable=self.pixel_size, background='#ECECEC', activebackground='#ECECEC', highlightthickness=0).pack(side=tk.LEFT, padx=6)
        tk.Radiobutton(pim, text="790px", value="790", variable=self.pixel_size, background='#ECECEC', activebackground='#ECECEC', highlightthickness=0).pack(side=tk.LEFT, padx=6)

        actions = ttk.Frame(content)
        actions.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(actions, text="取消", command=self.window.destroy).pack(side=tk.RIGHT)
        ttk.Button(actions, text="保存", command=self._save).pack(side=tk.RIGHT, padx=8)

    def _path_row(self, parent, label, value):
        row = tk.Frame(parent, background='#ECECEC')
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, width=12, background='#ECECEC').pack(side=tk.LEFT)
        entry = ttk.Entry(row)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        entry.insert(0, value)
        ttk.Button(row, text="浏览", command=lambda: self._select_directory(entry, label)).pack(side=tk.LEFT)
        return entry

    def _select_directory(self, entry, title):
        path = filedialog.askdirectory(title=f"选择{title}", parent=self.window)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _select_browser(self):
        file_types = [("Chrome", "chrome.exe")] if platform.system() == "Windows" else [("Chrome", "*")]
        path = filedialog.askopenfilename(title="选择 Chrome 浏览器", filetypes=file_types, parent=self.window)
        if path:
            self.chrome_path.delete(0, tk.END)
            self.chrome_path.insert(0, path)

    def _test_browser(self):
        path = self.chrome_path.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("错误", "请选择有效的 Chrome 浏览器路径", parent=self.window)
            return

        def complete(success, message):
            def show_result():
                if success:
                    messagebox.showinfo("成功", message, parent=self.window)
                else:
                    messagebox.showerror("错误", message, parent=self.window)
            self.window.after(0, show_result)

        self.browser_initializer.start_test_thread(path, complete_callback=complete)

    def _save(self):
        try:
            values = {
                'log_export_path': self.log_path.get().strip(),
                'task_result_path': self.result_path.get().strip(),
                'config_path': self.config_path.get().strip(),
                'chrome_path': self.chrome_path.get().strip(),
            }
            for key, value in values.items():
                if not value:
                    raise ValueError("路径设置不能为空")
                if key != 'chrome_path':
                    os.makedirs(value, exist_ok=True)
            self.settings.settings.update(values)
            self.settings.settings['browser_settings'] = {'auto_close': self.auto_close.get()}
            self.settings.settings['pim_settings'] = {'pixel_size': self.pixel_size.get()}
            self.settings.save_settings()
            logging.info("设置已保存")
            if self.on_saved:
                self.on_saved()
            messagebox.showinfo("成功", "设置已保存", parent=self.window)
            self.window.destroy()
        except Exception as error:
            messagebox.showerror("保存失败", str(error), parent=self.window)
