import tkinter as tk
from tkinter import messagebox
import logging
import os
from datetime import datetime
from tkinter import ttk
from common.settings import Settings as AppSettings
from common.config_schema import PIM_HEADERS
from common.config_generator import generate_config_workbook
from common.data_editor import DataEditor
from common.file_dialogs import choose_directory, choose_excel_file, open_file
from common.task_models import PimTaskRequest, TaskCallbacks, TaskResult
from common.task_runner import TaskRunner
from common.log_policy import is_diagnostic_message
from pim.task import PimTask


def load_shared_pim_settings():
    """读取 DDAS PLUS 的统一浏览器与 PIM 设置。"""
    app_settings = AppSettings()
    app_settings.load_settings()
    return {
        'browser_path': app_settings.settings.get('chrome_path', ''),
        'pixel_size': app_settings.settings.get('pim_settings', {}).get('pixel_size', '750'),
    }


class PimScriptGUI:
    def __init__(self, master, container=None, shared_log_text=None, shared_status=None):
        self.master = master
        self.shared_status = shared_status
        if container is None:
            master.title("PIM CAS version 1.1.1")
        host = container or master

        # 创建一个框架来容纳所有控件
        self.main_frame = ttk.Frame(host)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.config_path = tk.StringVar()
        self.pc_value_var = tk.BooleanVar()
        self.mobile_value_var = tk.BooleanVar()
        self.pc_image_var = tk.BooleanVar()
        self.mobile_image_var = tk.BooleanVar()
        self.preset_module_var = tk.BooleanVar()
        self.data_editor = DataEditor()

        page = ttk.Frame(self.main_frame, padding=12)
        page.pack(fill=tk.BOTH, expand=True)

        config_frame = tk.LabelFrame(page, text="配置数据", background='#ECECEC', borderwidth=1, relief=tk.SOLID, highlightthickness=0, padx=12, pady=12)
        config_frame.pack(fill=tk.X, pady=(0, 10))
        path_row = tk.Frame(config_frame, background='#ECECEC')
        path_row.pack(fill=tk.X)
        tk.Label(path_row, text="配置文件:", background='#ECECEC').pack(side=tk.LEFT, padx=(0, 8))
        self.config_entry = ttk.Entry(path_row, textvariable=self.config_path, state='readonly')
        self.config_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.config_entry.bind("<Double-1>", self.open_config_file)
        self.config_button = ttk.Button(path_row, text="配置数据", style='Batch.Small.TButton')
        self.config_button.pack(side=tk.LEFT, padx=5)
        self.edit_button = ttk.Button(path_row, text="编辑数据", style='Batch.Small.TButton')
        self.edit_button.pack(side=tk.LEFT, padx=(5, 0))

        config_menu = tk.Menu(path_row, tearoff=0)
        config_menu.add_command(label="选择配置文件", command=self.browse_config)
        config_menu.add_command(label="选择图片文件夹", command=self.generate_config)

        def show_config_menu(event):
            config_menu.post(
                event.widget.winfo_rootx(),
                event.widget.winfo_rooty() + event.widget.winfo_height(),
            )

        self.config_button.bind('<Button-1>', show_config_menu)

        edit_menu = tk.Menu(path_row, tearoff=0)
        edit_menu.add_command(label="查看数据", command=self.open_config_file)
        edit_menu.add_command(label="数据编辑器", command=self.edit_config)

        def show_edit_menu(event):
            edit_menu.post(
                event.widget.winfo_rootx(),
                event.widget.winfo_rooty() + event.widget.winfo_height(),
            )

        self.edit_button.bind('<Button-1>', show_edit_menu)

        options_frame = tk.LabelFrame(page, text="执行内容", background='#ECECEC', borderwidth=1, relief=tk.SOLID, highlightthickness=0, padx=12, pady=12)
        options_frame.pack(fill=tk.X, pady=(0, 10))
        options = tk.Frame(options_frame, background='#ECECEC')
        options.pack(fill=tk.X)
        for text, variable in (("填PC选项值", self.pc_value_var), ("填移动选项值", self.mobile_value_var), ("传PC图片", self.pc_image_var), ("传移动图片", self.mobile_image_var)):
            tk.Checkbutton(options, text=text, variable=variable, background='#ECECEC', activebackground='#ECECEC', highlightthickness=0).pack(side=tk.LEFT, padx=(0, 12))

        preset_frame = tk.LabelFrame(page, text="其他模式", background='#ECECEC', borderwidth=1, relief=tk.SOLID, highlightthickness=0, padx=12, pady=12)
        preset_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Checkbutton(preset_frame, text="配置预设模块", variable=self.preset_module_var, background='#ECECEC', activebackground='#ECECEC', highlightthickness=0).pack(anchor=tk.W)

        ttk.Label(
            page,
            text="提示：PC图和移动图目前只能二选一，后上传的图片会覆盖先上传的图片。\n"
                 "开始前请在 PIM 页面打开文案列表 → 配置映射 → 添加文案字段 → 选择组件类型。",
            foreground="gray",
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(0, 10))

        button_frame = ttk.Frame(page)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.start_button = ttk.Button(button_frame, text="开始", command=self.start_task, style='Batch.TButton')
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.stop_button = ttk.Button(button_frame, text="终止", command=self.stop_process, state=tk.DISABLED, style='Batch.TButton')
        self.stop_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        self.task_runner = TaskRunner()
        self.stop_flag = self.task_runner.stop_event
        self.active_task = None

        # 初始化日志
        self._emit_log("GUI 初始化完成")

    def edit_config(self):
        """使用深绘与 PIM 共用的数据编辑器。"""
        self.data_editor.show_file(self.config_path.get(), parent=self.master)

    def _emit_log(self, message):
        if not is_diagnostic_message(message):
            return
        logging.info("[PIM] %s", message)

    def generate_config(self):
        self._emit_log("开始生成配置文件...")
        folder_path = choose_directory("选择图片文件夹")
        if not folder_path:
            self._emit_log("未选择文件夹,取消生成配置文件")
            return

        self._emit_log(f"选择的文件夹路径: {folder_path}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_filename = f"PimScript_{timestamp}.xlsx"
        full_excel_path = os.path.join(folder_path, excel_filename)
        result = generate_config_workbook(folder_path, full_excel_path, PIM_HEADERS)
        self._emit_log(f"已添加 {result['image_count']} 张图片")
        self._emit_log(f"配置文件保存为: {full_excel_path}")

        self.config_path.set(full_excel_path)
        self._emit_log("配置文件路径已更新")

    def open_config_file(self, event=None):
        self._emit_log("尝试打开配置文件...")
        if self.config_path.get():
            open_file(self.config_path.get())
            self._emit_log(f"打开文件: {self.config_path.get()}")
        else:
            self._emit_log("配置文件路径为空")

    def browse_config(self):
        self._emit_log("浏览配置文件...")
        filename = choose_excel_file()
        if filename:
            self.config_path.set(filename)
            self._emit_log(f"选择的配文件: {filename}")
        else:
            self._emit_log("未选择文件")

    def start_task(self):
        # 校验复选框状态
        inner_checkboxes_selected = (self.pc_value_var.get() or
                                    self.mobile_value_var.get() or
                                    self.pc_image_var.get() or
                                    self.mobile_image_var.get())

        preset_module_selected = self.preset_module_var.get()

        if inner_checkboxes_selected and preset_module_selected:
            messagebox.showerror("错误", "配置预设模块与其他功能不能同时勾选，请只选择一种功能")
            self._emit_log("错误: 配置预设模块与其他功能不能同时勾选")
            return

        # 检查如果勾选了配置预设模块，但没有选择配置文件
        if preset_module_selected and not self.config_path.get():
            messagebox.showerror("错误", "未选择配置文件。请先生成或选择配置文件。")
            self._emit_log("错误: 未选择配置文件")
            return

        self._emit_log("启动处理线程...")
        shared_settings = load_shared_pim_settings()
        request = PimTaskRequest(
            config_path=self.config_path.get(),
            fill_pc_value=self.pc_value_var.get(),
            fill_mobile_value=self.mobile_value_var.get(),
            upload_pc_image=self.pc_image_var.get(),
            upload_mobile_image=self.mobile_image_var.get(),
            preset_module=self.preset_module_var.get(),
            pixel_size=shared_settings.get('pixel_size', '750'),
        )
        callbacks = TaskCallbacks(
            log=lambda message: logging.info("[PIM] %s", message),
            status=self.update_task_status,
            error=lambda message: self.master.after(0, lambda: messagebox.showerror("错误", message)),
            confirm=self.confirm_business_action,
            finished=lambda: self.master.after(0, self.finish_task_ui),
            info=lambda message: self.master.after(0, lambda: messagebox.showinfo("任务完成", message)),
            warning=lambda message: self.master.after(0, lambda: messagebox.showwarning("警告", message)),
        )
        task = PimTask(request, callbacks, self.task_runner.stop_event)
        self.active_task = task
        if not self.task_runner.start_task_thread(task.run):
            messagebox.showwarning("提示", "PIM 任务已在运行")
            return
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

    def confirm_business_action(self, message):
        result = []
        done = __import__('threading').Event()
        def ask():
            result.append(messagebox.askyesno("提示", message))
            done.set()
        self.master.after(0, ask)
        done.wait()
        return result[0]

    def finish_task_ui(self):
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def update_task_status(self, message):
        if self.shared_status is not None:
            self.master.after(0, lambda: self.shared_status.configure(text=message))
        self._emit_log(message)

    def stop_process(self):
        self._emit_log("终止处理...")
        self.stop_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.task_runner.stop_task_thread(
            self.active_task,
            callback=lambda: self.master.after(0, self.finish_stopped_ui),
        )

    def finish_stopped_ui(self):
        self.stop_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)
        self.update_task_status("已终止")
        self._emit_log("已终止，启用启动按钮")
