import logging
import os
import platform
import tkinter as tk
import tkinter.scrolledtext as scrolledtext
from tkinter import messagebox, ttk

from common.logger import TextHandler
from common.settings import Settings
from common.unified_settings import UnifiedSettingsDialog
from deedraw.view import GUI
from pim.view import PimScriptGUI

APP_VERSION = "1.3.10"


class UnifiedApp:
    """Single-window DDAS PLUS shell for Deedraw and PIM."""

    WINDOW_WIDTH = 552
    WINDOW_HEIGHT = 700
    WINDOW_SIZE = f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}"

    def __init__(self, root):
        self.root = root
        self.current_page = None
        self.root.title(f"DDAS PLUS v{APP_VERSION}")
        self.root.geometry(self.WINDOW_SIZE)
        self.root.minsize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.root.maxsize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.root.resizable(False, False)

        self.settings = Settings()
        self.settings.load_settings()
        self._configure_styles()
        self._build_shell()

        self.logger = TextHandler(self.log_text, self.settings.settings)
        self.log_file = self.logger.setup_logging()
        self.show_home()
        logging.info("DDAS PLUS v%s 已启动，日志文件: %s", APP_VERSION, self.log_file)

    def _configure_styles(self):
        style = ttk.Style()
        white = "#FFFFFF"
        style.configure("AppTitle.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("White.TFrame", background=white)
        style.configure("White.TLabel", background=white)
        style.configure("White.TCheckbutton", background=white)
        style.configure("White.TRadiobutton", background=white)
        style.configure("White.TLabelframe", background=white)
        style.configure("White.TLabelframe.Label", background=self.root.cget("background"))
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 9))

    def _build_shell(self):
        topbar = ttk.Frame(self.root, padding=(14, 10))
        topbar.pack(fill=tk.X)
        ttk.Button(topbar, text="首页", command=self.show_home).pack(side=tk.LEFT)
        self.page_title = ttk.Label(topbar, text="选择工具")
        self.page_title.pack(side=tk.LEFT, padx=(18, 0))
        ttk.Button(topbar, text="设置", command=self.show_settings).pack(side=tk.RIGHT, padx=10)

        separator = ttk.Separator(self.root, orient=tk.HORIZONTAL)
        separator.pack(fill=tk.X)

        self.content = ttk.Frame(self.root, padding=(14, 10))
        self.content.pack(fill=tk.BOTH, expand=True)

        log_panel = ttk.Frame(self.root, padding=(8, 6))
        log_panel.pack(fill=tk.X, padx=14, pady=(0, 12))
        log_header = ttk.Frame(log_panel)
        log_header.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(log_header, text="日志", font=("Microsoft YaHei UI", 10, "bold")).pack(side=tk.LEFT)
        self.task_status = ttk.Label(log_header, text="就绪", style="Status.TLabel")
        self.task_status.pack(side=tk.RIGHT)
        self.log_text = scrolledtext.ScrolledText(
            log_panel,
            wrap=tk.WORD,
            height=7,
            highlightthickness=0,
            borderwidth=0,
        )
        self.log_text.pack(fill=tk.X)
        controls = ttk.Frame(log_panel)
        controls.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(controls, text="清屏", command=lambda: self.logger.clear_log()).pack(side=tk.LEFT)
        ttk.Button(controls, text="导出日志", command=lambda: self.logger.export_log()).pack(side=tk.LEFT, padx=6)

    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()
        self.current_page = None

    def _can_leave_page(self):
        if self.current_page is None:
            return True
        running = bool(getattr(self.current_page, "running", False))
        runner = getattr(self.current_page, "task_runner", None)
        if runner is not None and runner.is_running():
            running = True
        if running:
            messagebox.showwarning("任务运行中", "请先停止当前任务，再切换页面。", parent=self.root)
            return False
        return True

    def show_home(self):
        if not self._can_leave_page():
            return
        self._clear_content()
        self.page_title.config(text="选择工具")
        self.task_status.config(text="就绪")

        page = ttk.Frame(self.content, padding=24)
        page.pack(fill=tk.BOTH, expand=True)
        ttk.Label(page, text="选择自动化工具", font=("Microsoft YaHei UI", 20, "bold")).pack(pady=(18, 26))
        cards = ttk.Frame(page)
        cards.pack(fill=tk.BOTH, expand=True)
        for column in (0, 1):
            cards.columnconfigure(column, weight=1, uniform="product")
        cards.rowconfigure(0, weight=1)
        self._card(cards, 0, "深绘", self.show_deedraw)
        self._card(cards, 1, "PIM", self.show_pim)

    def _card(self, parent, column, title, command):
        background = "#FFFFFF"
        card = tk.Frame(
            parent,
            background=background,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#B8B8B8",
            cursor="hand2",
        )
        card.grid(row=0, column=column, sticky="nsew", padx=12, pady=8)
        title_label = tk.Label(
            card,
            text=title,
            background=background,
            font=("Microsoft YaHei UI", 20, "bold"),
            cursor="hand2",
        )
        title_label.pack(fill=tk.BOTH, expand=True)

        for widget in (card, title_label):
            widget.bind("<Button-1>", lambda _event, action=command: action())
            widget.bind("<Enter>", lambda _event, panel=card: panel.configure(highlightbackground="#7A7A7A"))
            widget.bind("<Leave>", lambda _event, panel=card: panel.configure(highlightbackground="#B8B8B8"))

    def show_deedraw(self):
        if not self._can_leave_page():
            return
        self._clear_content()
        self.page_title.config(text="深绘")
        self.task_status.config(text="就绪")
        self.current_page = GUI(
            self.root,
            container=self.content,
            shared_log_text=self.log_text,
            shared_logger=self.logger,
            shared_status=self.task_status,
            shared_settings=self.settings,
        )

    def show_pim(self):
        if not self._can_leave_page():
            return
        self._clear_content()
        self.page_title.config(text="PIM")
        self.task_status.config(text="就绪")
        self.current_page = PimScriptGUI(
            self.root,
            container=self.content,
            shared_log_text=self.log_text,
            shared_status=self.task_status,
        )

    def show_settings(self):
        UnifiedSettingsDialog(self.root, self.settings, on_saved=self._settings_saved)

    def _settings_saved(self):
        self.logger.settings = self.settings.settings
        self.log_file = self.logger.setup_logging()


if __name__ == "__main__":
    root = tk.Tk()
    if platform.system() == "Windows":
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    app = UnifiedApp(root)
    root.mainloop()
