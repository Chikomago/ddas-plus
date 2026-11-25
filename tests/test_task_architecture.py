import ast
import json
import threading
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from common.task_models import DeedrawFieldRequest, DeedrawTaskRequest, PimTaskRequest, TaskCallbacks, TaskResult
from deedraw.task import DeedrawTask
from pim.task import PimTask
from common.task_results import TaskReport, format_task_report
from common.task_runner import TaskRunner
from common.log_policy import is_diagnostic_message


class TaskArchitectureTests(unittest.TestCase):
    def test_task_modules_have_no_tk_dependencies(self):
        project = Path(__file__).resolve().parent.parent
        forbidden_names = {"tkinter", "messagebox", "filedialog", "Entry", "BooleanVar", "Button"}
        for relative in ("deedraw/task.py", "pim/task.py"):
            tree = ast.parse((project / relative).read_text(encoding="utf-8"))
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            imports = {
                alias.name.split('.')[0]
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            self.assertFalse((names | imports) & forbidden_names, relative)

    def test_pim_task_accepts_plain_request(self):
        messages = []
        request = PimTaskRequest("a.xlsx", True, False, False, False, False, "750")
        callbacks = TaskCallbacks(messages.append, messages.append, messages.append)
        task = PimTask(request, callbacks)
        task.settings = {}
        task.run_task_logic = lambda value: TaskResult(True, "任务完成")
        result = task.run()
        self.assertTrue(result.success)

    def test_browser_operations_live_in_task_modules(self):
        project = Path(__file__).resolve().parent.parent
        deedraw = (project / "deedraw/task.py").read_text(encoding="utf-8")
        pim = (project / "pim/task.py").read_text(encoding="utf-8")
        for operation in (".ele(", ".click(", ".input("):
            self.assertIn(operation, deedraw)
            self.assertIn(operation, pim)

    def test_views_have_no_browser_element_operations(self):
        project = Path(__file__).resolve().parent.parent
        for relative in ("deedraw/view.py", "pim/view.py"):
            source = (project / relative).read_text(encoding="utf-8")
            for operation in (".ele(", ".eles(", ".click(", ".input(", ".run_js("):
                self.assertNotIn(operation, source, f"{operation} 不应出现在 {relative}")

    def test_browser_initialization_is_shared(self):
        project = Path(__file__).resolve().parent.parent
        for relative in ("deedraw/task.py", "pim/task.py"):
            source = (project / relative).read_text(encoding="utf-8")
            self.assertIn("create_browser(", source)
            self.assertNotIn("ChromiumOptions(", source)
            self.assertNotIn("ChromiumPage(", source)

    def test_browser_testing_is_shared(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "common/unified_settings.py").read_text(encoding="utf-8")
        self.assertIn("BrowserInitializer", source)
        self.assertNotIn("ChromiumOptions(", source)
        self.assertNotIn("ChromiumPage(", source)
        deedraw_source = (project / "deedraw/view.py").read_text(encoding="utf-8")
        self.assertNotIn("BrowserInitializer", deedraw_source)
        self.assertNotIn("test_chrome_browser", deedraw_source)
        pim_source = (project / "pim/view.py").read_text(encoding="utf-8")
        self.assertNotIn("BrowserInitializer", pim_source)
        self.assertNotIn("SettingsWindow", pim_source)
        self.assertNotIn("open_settings", pim_source)

    def test_deedraw_view_has_no_log_shell(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "deedraw/view.py").read_text(encoding="utf-8")
        for phrase in ("ScrolledText", "TextHandler", "clear_log", "export_log", "setup_logging"):
            self.assertNotIn(phrase, source)

    def test_product_views_share_shell_and_runner_contract(self):
        project = Path(__file__).resolve().parent.parent
        main_source = (project / "main.py").read_text(encoding="utf-8")
        for relative in ("deedraw/view.py", "pim/view.py"):
            source = (project / relative).read_text(encoding="utf-8")
            self.assertIn("self.task_runner", source)
            self.assertNotIn("thread_manager", source)
            self.assertNotIn("process_thread", source)
        self.assertNotIn("thread_manager", main_source)
        self.assertNotIn("process_thread", main_source)

    def test_pim_view_has_no_private_log_shell(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "pim/view.py").read_text(encoding="utf-8")
        self.assertNotIn("ScrolledText", source)
        self.assertNotIn("scrolledtext", source)
        self.assertNotIn("self.log_text", source)

    def test_pim_task_uses_callbacks_directly(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "pim/task.py").read_text(encoding="utf-8")
        self.assertNotIn("_MessageBridge", source)
        self.assertNotIn("messagebox", source)

    def test_deedraw_instructions_are_removed(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "deedraw/view.py").read_text(encoding="utf-8")
        for phrase in ("操作说明", "show_instructions", "download_instruction_images", "step1.png"):
            self.assertNotIn(phrase, source)

    def test_browser_support_is_consolidated(self):
        project = Path(__file__).resolve().parent.parent
        settings_source = (project / "common/unified_settings.py").read_text(encoding="utf-8")
        self.assertIn("open_chrome_download", settings_source)
        self.assertFalse((project / "common/download_chrome.py").exists())

    def test_main_window_and_home_cards(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "main_tk.py").read_text(encoding="utf-8")
        self.assertIn("WINDOW_WIDTH = 552", source)
        self.assertIn("WINDOW_HEIGHT = 700", source)
        self.assertIn("self.root.resizable(False, False)", source)
        self.assertIn("card = tk.Frame(", source)
        self.assertIn('widget.bind("<Button-1>"', source)
        self.assertNotIn('text=f"进入{title}"', source)
        self.assertNotIn("Card.TFrame", source)
        self.assertNotIn("HomeCard.TButton", source)

    def test_deedraw_layout_does_not_use_compressed_relative_heights(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "deedraw/view.py").read_text(encoding="utf-8")
        self.assertNotIn("login_frame.place", source)
        self.assertNotIn("account_frame.place", source)
        self.assertNotIn("password_frame.place", source)
        self.assertNotIn("fields_frame.place", source)
        self.assertIn("self.batch_canvas.itemconfigure", source)

    def test_project_uses_logging_instead_of_self_log(self):
        project = Path(__file__).resolve().parent.parent
        for relative in ("deedraw/task.py", "deedraw/view.py", "pim/task.py", "pim/view.py"):
            source = (project / relative).read_text(encoding="utf-8")
            self.assertNotIn("self.log(", source, relative)
            self.assertNotIn("def log(", source, relative)

    def test_shared_task_report(self):
        message = format_task_report(TaskReport(3, 2, 1, 65.5, failure_details=["第三项失败"]))
        self.assertIn("总任务数：3", message)
        self.assertIn("完成任务数：2", message)
        self.assertIn("1分5.50秒", message)

    def test_deedraw_reuses_authenticated_cookie_session(self):
        from deedraw.task import TaskProcessor

        class Wait:
            def doc_loaded(self):
                pass

        class Browser:
            def __init__(self):
                self.url = ""
                self.wait = Wait()
                self.visited = []

            def get(self, url):
                self.visited.append(url)
                if url.endswith("/login"):
                    self.url = "https://www.deepdraw.biz/authorized/merchant/home"
                else:
                    self.url = url

            def ele(self, *_args, **_kwargs):
                raise AssertionError("Cookie 有效时不应查找登录表单")

        callbacks = TaskCallbacks(lambda _: None, lambda _: None, lambda _: None)
        processor = TaskProcessor(TaskRunner(), callbacks)
        processor.browser = Browser()
        processor.request = SimpleNamespace(username="", password="")

        self.assertTrue(processor.login())
        self.assertEqual(processor.browser.visited[-1], processor.FIELD_SETTINGS_URL)

    def test_deedraw_credentials_are_only_required_for_login_form(self):
        project = Path(__file__).resolve().parent.parent
        view_source = (project / "deedraw/view.py").read_text(encoding="utf-8")
        self.assertNotIn('messagebox.showerror("错误", "请输入账号和密码")', view_source)

    def test_deedraw_resets_running_state_before_login(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "deedraw/task.py").read_text(encoding="utf-8")
        run_task = source[source.index("    def run_task(self, request):"):source.index("    def show_error", source.index("    def run_task(self, request):"))]
        self.assertLess(run_task.index("self.running = True"), run_task.index("self.login()"))

    def test_deedraw_completion_is_not_treated_as_stop(self):
        from deedraw.task import TaskProcessor

        callbacks = TaskCallbacks(lambda _: None, lambda _: None, lambda _: None)
        runner = TaskRunner()
        processor = TaskProcessor(runner, callbacks)
        processor.running = False
        self.assertFalse(processor.is_stop_requested())
        processor.request_stop()
        self.assertTrue(processor.is_stop_requested())

    def test_focus_borders_and_section_backgrounds(self):
        project = Path(__file__).resolve().parent.parent
        main_source = (project / "main_tk.py").read_text(encoding="utf-8")
        deedraw_source = (project / "deedraw/view.py").read_text(encoding="utf-8")
        pim_source = (project / "pim/view.py").read_text(encoding="utf-8")
        settings_source = (project / "common/unified_settings.py").read_text(encoding="utf-8")

        self.assertIn("highlightthickness=0", main_source)
        self.assertIn("highlightthickness=0", deedraw_source)
        self.assertIn('white = "#FFFFFF"', main_source)
        self.assertIn('background = "#FFFFFF"', main_source)
        self.assertIn("padx=(18, 0)", main_source)
        for source in (deedraw_source, pim_source, settings_source):
            self.assertIn("tk.LabelFrame", source)
            self.assertIn("background='#ECECEC'", source)
            self.assertIn("borderwidth=1", source)
            self.assertIn("relief=tk.SOLID", source)
            self.assertNotIn("White.TLabelframe", source)

    def test_windows_field_row_stretches_to_both_edges(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "deedraw/view.py").read_text(encoding="utf-8")
        self.assertIn("height=210", source)
        self.assertIn("input_frame.grid_columnconfigure(2, weight=1", source)
        self.assertIn("input_frame.grid_columnconfigure(3, weight=1", source)
        self.assertIn("file_btn.grid(row=0, column=2, sticky='ew'", source)
        self.assertIn("edit_btn.grid(row=0, column=3, sticky='ew'", source)
        self.assertIn("add_btn.grid(row=0, column=4, sticky='e'", source)
        self.assertNotIn("file_btn.pack", source)

    def test_window_title_version_matches_manifest(self):
        project = Path(__file__).resolve().parent.parent
        manifest = json.loads((project / "plugin.json").read_text(encoding="utf-8"))
        source = (project / "main.py").read_text(encoding="utf-8")
        self.assertIn(f'APP_VERSION = "{manifest["version"]}"', source)
        self.assertIn('webview.create_window(f"DDAS PLUS v{APP_VERSION}"', source)

    def test_workflow_builds_both_macos_architectures(self):
        project = Path(__file__).resolve().parent.parent
        workflow = (project / ".github/workflows/build.yml").read_text(encoding="utf-8")
        self.assertIn("os: macos-15\n            name: macOS Apple Silicon", workflow)
        self.assertIn("os: macos-15-intel\n            name: macOS Intel", workflow)
        self.assertIn("DDAS-PLUS-macOS-Apple-Silicon.zip", workflow)
        self.assertIn("DDAS-PLUS-macOS-Intel.zip", workflow)

    def test_shared_task_stop_lifecycle(self):
        runner = TaskRunner()
        stopped = threading.Event()

        class Task:
            def request_stop(self):
                stopped.set()

        runner.start_task_thread(lambda: stopped.wait(1))
        runner.stop_task_thread(Task())
        self.assertTrue(stopped.wait(1))

    def test_tasks_expose_common_stop_hook(self):
        self.assertTrue(hasattr(PimTask, "request_stop"))
        from deedraw.task import TaskProcessor
        self.assertTrue(hasattr(TaskProcessor, "request_stop"))

    def test_log_policy_removes_click_stream(self):
        for message in ("已点击提交按钮", "正在查找登录按钮", "当前URL: https://example.com"):
            self.assertFalse(is_diagnostic_message(message))
        for message in ("未找到保存按钮", "图片上传超时", "任务已终止"):
            self.assertTrue(is_diagnostic_message(message))

    def test_task_source_has_no_action_success_logs(self):
        project = Path(__file__).resolve().parent.parent
        source = "\n".join(
            (project / relative).read_text(encoding="utf-8")
            for relative in ("deedraw/task.py", "pim/task.py")
        )
        for phrase in ("'确 定'操作完成", "确认按钮点击成功", "登录按钮点击完成", "已在输入框中输入"):
            self.assertNotIn(phrase, source)

    def test_deedraw_config_adapter_has_no_result_export(self):
        project = Path(__file__).resolve().parent.parent
        source = (project / "deedraw/config_adapter.py").read_text(encoding="utf-8")
        self.assertNotIn("export_task_results", source)
        self.assertNotIn("export_results", source)
        self.assertNotIn("openpyxl.Workbook", source)
        self.assertNotIn("filedialog.", source)

    def test_deedraw_task_accepts_plain_request(self):
        request = DeedrawTaskRequest(
            [DeedrawFieldRequest("color", "data.xlsx", False, True, False, False)],
            {"chrome_path": "/browser"},
        )
        callbacks = TaskCallbacks(lambda _: None, lambda _: None, lambda _: None)
        result = DeedrawTask(request, callbacks).run(
            lambda value: TaskResult(value.fields[0].fill_pc_value)
        )
        self.assertTrue(result.success)


    def test_version_history_button_matches_manifest(self):
        project = Path(__file__).resolve().parent.parent
        manifest = json.loads((project / "plugin.json").read_text(encoding="utf-8"))
        main_jsx = (project / "frontend/src/main.jsx").read_text(encoding="utf-8")
        changelog = (project / "frontend/src/changelog.js").read_text(encoding="utf-8")
        styles = (project / "frontend/src/window.css").read_text(encoding="utf-8")
        self.assertIn('aria-label="更新"', main_jsx)
        self.assertIn("setModal('changelog')", main_jsx)
        self.assertIn("CHANGELOG", main_jsx)
        self.assertIn(f"version: '{manifest['version']}'", changelog)
        self.assertIn(".changelog-release", styles)


if __name__ == "__main__":
    unittest.main()
