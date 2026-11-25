import tkinter as tk
from tkinter import ttk
import logging
from tkinter import messagebox
from deedraw.config_adapter import DeedrawConfigAdapter
from common.data_editor import DataEditor
from common.task_runner import TaskRunner
from common.task_models import DeedrawFieldRequest, DeedrawTaskRequest
from deedraw.task import TaskProcessor
from common.task_models import TaskCallbacks
from common.settings import Settings
from common.file_dialogs import choose_directory
import threading

class GUI:
    def __init__(self, root, container=None, shared_log_text=None, shared_logger=None, shared_status=None, shared_settings=None):
        self.root = root
        self.embedded = container is not None
        if not self.embedded:
            self.root.title("DDAS v3.0.10")
            self.root.geometry('540x700')
        host = container or self.root

        # 创建主框架
        self.main_frame = ttk.Frame(host)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 初始化设置
        self.settings = shared_settings or Settings()
        if shared_settings is None:
            self.settings.load_settings()

        # 初始化模块
        self.file_handler = DeedrawConfigAdapter(settings=self.settings.settings)
        self.logger = shared_logger
        self.data_editor = DataEditor()
        self.task_runner = TaskRunner()
        self.task_status = shared_status or ttk.Label(self.main_frame, text="就绪", style='Status.TLabel')
        if shared_status is None:
            self.task_status.pack(anchor=tk.E, padx=5)
        self.task_processor = TaskProcessor(
            self.task_runner,
            TaskCallbacks(
                log=logging.info,
                info=lambda text: self.root.after(0, lambda: messagebox.showinfo("任务完成", text)),
                warning=lambda text: self.root.after(0, lambda: messagebox.showwarning("警告", text)),
                status=lambda text: self.root.after(0, lambda: self.task_status.configure(text=text)),
                error=lambda text: self.root.after(0, lambda: messagebox.showerror("错误", text)),
                confirm=self.confirm_task_result,
                finished=lambda: self.root.after(0, lambda: self.start_button.configure(text="开始")),
            ),
        )

        # 初始化字段行列表
        self.field_rows = []

        # 初始化默认复选框变量
        self.default_pc_pic_var = tk.BooleanVar(value=False)
        self.default_pc_opt_var = tk.BooleanVar(value=False)
        self.default_mobile_pic_var = tk.BooleanVar(value=False)
        self.default_mobile_opt_var = tk.BooleanVar(value=False)

        # 设置状态样式
        style = ttk.Style()
        style.configure('Status.TLabel',
            font=('Microsoft YaHei UI', 9)
        )

        # 初始化运行状态
        self.running = False

        logging.info("准备就绪")

        # 设置模式
        self.mode = "batch"

        # 创建批量模式框架
        self.batch_mode_frame = ttk.Frame(self.main_frame)
        self.batch_mode_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(12, 10))

        # 字段列表框架
        fields_frame = tk.LabelFrame(
            self.batch_mode_frame,
            text='字段列表',
            background='#ECECEC', borderwidth=1, relief=tk.SOLID,
            highlightthickness=0,
        )
        fields_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 8))

        # 创建滚动区域
        self.batch_canvas = tk.Canvas(
            fields_frame,
            background="#ECECEC",
            height=210,
            highlightthickness=0,
            borderwidth=0,
        )
        self.batch_scrollbar = ttk.Scrollbar(fields_frame, orient="vertical", command=self.batch_canvas.yview)
        self.batch_scrollable_frame = tk.Frame(self.batch_canvas, background='#ECECEC')

        self.batch_canvas.configure(yscrollcommand=self.batch_scrollbar.set)

        # 打包滚动条和画布
        self.batch_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.batch_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 创建窗口来显示可滚动框架
        self.batch_canvas_frame = self.batch_canvas.create_window((0, 0), window=self.batch_scrollable_frame, anchor="nw")

        # 配置画布滚动
        def configure_scroll(event):
            self.batch_canvas.configure(scrollregion=self.batch_canvas.bbox("all"))

        self.batch_scrollable_frame.bind('<Configure>', configure_scroll)
        self.batch_canvas.bind(
            '<Configure>',
            lambda event: self.batch_canvas.itemconfigure(self.batch_canvas_frame, width=event.width),
        )

        actions_frame = ttk.Frame(self.batch_mode_frame)
        actions_frame.pack(fill=tk.X)
        self.start_button = ttk.Button(
            actions_frame,
            text="开始",
            command=self.start_deedraw_task,
            style='Batch.TButton',
            state='disabled'  # 初始状态设为禁用
        )
        self.start_button.pack(side=tk.RIGHT, ipadx=28)

        # 添加第一个字段行
        self.add_batch_field_row(is_first=True)

    def confirm_task_result(self, message):
        """业务线程请求确认时，由 View 在主线程显示对话框。"""
        result = []
        done = threading.Event()
        def ask():
            result.append(messagebox.askyesno("任务完成", message))
            done.set()
        self.root.after(0, ask)
        done.wait()
        return result[0]

    def build_task_request(self):
        """在界面线程中读取控件，生成与 TTK 无关的任务快照。"""
        fields = []
        for row in self.field_rows:
            fields.append(DeedrawFieldRequest(
                code=row['field_entry'].get().strip(),
                config_path=row.get('file_path', ''),
                upload_pc_image=bool(row['pc_pic_var'].get()),
                fill_pc_value=bool(row['pc_opt_var'].get()),
                upload_mobile_image=bool(row['mobile_pic_var'].get()),
                fill_mobile_value=bool(row['mobile_opt_var'].get()),
            ))
        return DeedrawTaskRequest(
            fields=fields,
            settings=dict(self.settings.settings),
        )

    def start_deedraw_task(self):
        """只在 View 中处理控件状态，业务执行只接收任务快照。"""
        if self.task_runner.running:
            self.start_button.configure(text="正在终止...", state="disabled")
            self.task_runner.stop_task_thread(
                self.task_processor,
                callback=lambda: self.root.after(0, self.finish_deedraw_stop),
            )
            return
        request = self.build_task_request()
        self.start_button.configure(text="终止")
        if not self.task_processor.start(request):
            self.start_button.configure(text="开始")
            messagebox.showerror("错误", "启动任务失败")

    def finish_deedraw_stop(self):
        self.start_button.configure(text="开始", state="normal")
        self.task_status.configure(text="已终止")



    def add_batch_field_row(self, is_first=False):
        """添加批量字段行"""
        try:
            # 创建字段行的UI元素
            field_frame = tk.Frame(self.batch_scrollable_frame, background='#ECECEC')
            field_frame.pack(fill=tk.X, pady=(0 if is_first else 5), padx=5)

            # 字段编码和按钮框架
            input_frame = tk.Frame(field_frame, background='#ECECEC')
            input_frame.pack(fill=tk.X)
            input_frame.grid_columnconfigure(2, weight=1, uniform='field_action')
            input_frame.grid_columnconfigure(3, weight=1, uniform='field_action')

            # 字段编码输入
            code_frame = tk.Frame(input_frame, background='#ECECEC')
            code_frame.grid(row=0, column=0, sticky='w', padx=(2, 3))

            tk.Label(
                code_frame,
                text="字段名/编码:",
                background='#ECECEC'
            ).pack(side=tk.LEFT)

            code_entry = ttk.Entry(
                code_frame,
                width=7,
                style='Batch.TEntry'
            )
            code_entry.pack(side=tk.LEFT, padx=1)

            # 文件状态标签
            file_status_label = tk.Label(
                input_frame,
                text="✗",
                foreground='red', background='#ECECEC'
            )
            file_status_label.grid(row=0, column=1, padx=2)

            # 保存行信息
            row_info = {
                'frame': field_frame,
                'field_entry': code_entry,
                'file_status_label': file_status_label,
                'file_path': None,
                'pc_pic_var': tk.BooleanVar(value=self.default_pc_pic_var.get()),
                'pc_opt_var': tk.BooleanVar(value=self.default_pc_opt_var.get()),
                'mobile_pic_var': tk.BooleanVar(value=self.default_mobile_pic_var.get()),
                'mobile_opt_var': tk.BooleanVar(value=self.default_mobile_opt_var.get())
            }

            # 绑定事件
            code_entry.bind('<KeyRelease>', lambda e: self.check_start_button_state())
            row_info['pc_pic_var'].trace_add('write', lambda *args: self.check_start_button_state())
            row_info['pc_opt_var'].trace_add('write', lambda *args: self.check_start_button_state())
            row_info['mobile_pic_var'].trace_add('write', lambda *args: self.check_start_button_state())
            row_info['mobile_opt_var'].trace_add('write', lambda *args: self.check_start_button_state())

            self.field_rows.append(row_info)

            # 检查开始按钮状态
            self.check_start_button_state()

            # 打印当前字段行数
            logging.info(f"当前字段行数: {len(self.field_rows)}")  # 打印行数

            # 文件操作按钮
            file_btn = ttk.Button(
                input_frame,
                text="配置数据",
                width=8,
                style='Batch.Small.TButton'
            )
            file_btn.grid(row=0, column=2, sticky='ew', padx=2)

            # 创建文件操作菜单
            file_menu = tk.Menu(input_frame, tearoff=0)
            file_menu.add_command(
                label="选择配置文件",
                command=lambda: self.file_handler.browse_file_for_row(file_status_label, code_entry, self.field_rows)
            )
            file_menu.add_command(
                label="选择图片文件夹",
                command=lambda: self.file_handler.generate_excel_from_directory(
                    folder_path=choose_directory("选择图片文件夹"),
                    code_entry=code_entry,
                    field_rows=self.field_rows,
                    file_status_label=file_status_label
                )
            )

            # 绑定文件按钮点击事件
            def show_file_menu(event):
                file_menu.post(event.widget.winfo_rootx(), event.widget.winfo_rooty() + event.widget.winfo_height())

            file_btn.bind('<Button-1>', show_file_menu)

            # 编辑按钮
            edit_btn = ttk.Button(
                input_frame,
                text="编辑数据",
                width=8,
                style='Batch.Small.TButton'
            )
            edit_btn.grid(row=0, column=3, sticky='ew', padx=2)

            # 创建编辑菜单
            edit_menu = tk.Menu(input_frame, tearoff=0)
            edit_menu.add_command(
                label="查看数据",
                command=lambda: self.file_handler.view_file_for_row(code_entry, self.field_rows)
            )
            edit_menu.add_command(
                label="数据编辑器",
                command=lambda: self.data_editor.show_data_editor(code_entry, self.field_rows)
            )

            # 绑定编辑按钮点击事件
            def show_edit_menu(event):
                edit_menu.post(event.widget.winfo_rootx(), event.widget.winfo_rooty() + event.widget.winfo_height())

            edit_btn.bind('<Button-1>', show_edit_menu)

            # 复选框框架
            checkbox_frame = tk.Frame(field_frame, background='#ECECEC')
            checkbox_frame.pack(fill=tk.X, pady=5)

            checkbox_items = (
                ("上传PC图", row_info['pc_pic_var']),
                ("填PC选项值", row_info['pc_opt_var']),
                ("上传移动图", row_info['mobile_pic_var']),
                ("填移动选项值", row_info['mobile_opt_var']),
            )
            for column, (text, variable) in enumerate(checkbox_items):
                checkbox_frame.grid_columnconfigure(column, weight=1, uniform='field_option')
                tk.Checkbutton(
                    checkbox_frame,
                    text=text,
                    variable=variable,
                    background='#ECECEC', activebackground='#ECECEC', highlightthickness=0,
                ).grid(row=0, column=column, sticky='w', padx=5)

            # 添加/删除按钮
            if is_first:
                add_btn = ttk.Button(
                    input_frame,
                    text="+",
                    width=2,
                    command=lambda: self.add_batch_field_row(),
                    style='Batch.Small.TButton'
                )
                add_btn.grid(row=0, column=4, sticky='e', padx=(2, 0))
            else:
                del_btn = ttk.Button(
                    input_frame,
                    text="×",
                    width=2,
                    command=lambda: (
                        field_frame.destroy(),
                        self.field_rows.remove(row_info),
                        self.check_start_button_state()
                    ),
                    style='Batch.Small.TButton'
                )
                del_btn.grid(row=0, column=4, sticky='e', padx=(2, 0))

            # 添加分割线
            ttk.Separator(field_frame, orient='horizontal').pack(fill=tk.X, pady=5)

        except Exception as e:
            logging.error(f"添加字段行时出错: {str(e)}")
            messagebox.showerror("错误", f"添加字段行时出错: {str(e)}")

    def check_start_button_state(self):
        """检查并更新开始按钮状态"""
        # 如果没有字段行，禁用按钮
        if not self.field_rows:
            self.start_button.configure(state='disabled')
            return

        # 检查每一行是否都满足所有条件
        for row_info in self.field_rows:
            has_field_code = bool(row_info['field_entry'].get())  # 检查字段编码是否有输入
            has_file = row_info['file_status_label']['text'] != "✗"  # 检查文件状态
            has_checkbox = (  # 检查是否有复选框被选中
                row_info['pc_pic_var'].get() or
                row_info['pc_opt_var'].get() or
                row_info['mobile_pic_var'].get() or
                row_info['mobile_opt_var'].get()
            )

            # 如果任何一行不满足所有条件，禁用按钮并返回
            if not (has_field_code and has_file and has_checkbox):
                self.start_button.configure(state='disabled')
                return

        # 如果所有行都满足所有条件，启用按钮
        self.start_button.configure(state='normal')
