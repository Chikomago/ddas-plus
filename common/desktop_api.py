"""UI-independent desktop bridge. Browser automation remains in the task modules."""
from __future__ import annotations

import copy
import functools
import json
import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import uuid
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import openpyxl
from common.config_generator import generate_config_workbook, paired_rows, scan_images, write_config_rows
from common.config_loader import read_config
from common.config_schema import DEEDRAW_HEADERS, PIM_HEADERS, config_row, is_supported_image, validate_headers, RENAME_HEADER, VALUE_HEADERS
from common.log_policy import DiagnosticLogFilter
from common.task_models import DeedrawFieldRequest, DeedrawTaskRequest, PimTaskRequest, TaskCallbacks
from common.task_runner import TaskRunner


APP_VERSION = "2.0.11"
RELEASES_URL = "https://github.com/Chikomago/ddas-plus/releases"
LATEST_RELEASE_API = "https://api.github.com/repos/Chikomago/ddas-plus/releases/latest"


def _version_parts(tag):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag)
    if not match:
        raise ValueError("GitHub 发布版本号格式无效")
    return tuple(map(int, match.groups()))


def endpoint(function):
    @functools.wraps(function)
    def wrapped(self, *args, **kwargs):
        try:
            return {"ok": True, "value": function(self, *args, **kwargs)}
        except Exception as error:
            if isinstance(error, ValueError):
                logging.warning("%s", error)
            else:
                logging.exception("%s 失败", function.__name__)
            return {"ok": False, "message": str(error)}
    return wrapped


class BridgeLogHandler(logging.Handler):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.addFilter(DiagnosticLogFilter())
        self.ddas_plus_handler = True

    def emit(self, record):
        self.bridge._emit("log", text=record.getMessage(), level=record.levelname.lower(),
                          time=datetime.fromtimestamp(record.created).strftime("%H:%M:%S"))


class DesktopAPI:
    def __init__(self, settings=None):
        if settings is None:
            from common.settings import Settings
            settings = Settings()
            settings.load_settings()
        self.settings = settings
        self.window = None
        self.runner = TaskRunner()
        self.active_task = None
        self.status = "就绪"
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._last_state = None
        self._events = deque()
        self._pending = {}
        self._closed = False
        self._starting = False
        self._log_text = deque(maxlen=10000)
        self._editor_versions = {}

    def _emit(self, kind, **payload):
        with self._lock:
            if self._closed:
                return
            event = {"kind": kind, **payload}
            if kind == "log" and len(self._events) >= 5000:
                for index, old in enumerate(self._events):
                    if old["kind"] == "log":
                        del self._events[index]
                        break
            self._events.append(event)
            self._changed.notify_all()
            if kind == "log":
                self._log_text.append(f"{payload.get('time', '')} {payload['text']}")

    def _message(self, text, title="提示", level="info"):
        self._emit("message", title=title, text=str(text), level=level)

    def _status(self, text):
        with self._lock:
            if self.status != str(text):
                self.status = str(text)
                self._changed.notify_all()

    def _confirm(self, text, title="提示"):
        key, done = uuid.uuid4().hex, threading.Event()
        with self._lock:
            if self._closed or (self.runner.running and self.runner.stop_event.is_set()):
                return False
            pending = {"event": done, "answer": False, "text": str(text), "title": title}
            self._pending[key] = pending
        self._emit("confirm", id=key, title=title, text=str(text))
        done.wait()
        with self._lock:
            self._pending.pop(key, None)
        return pending["answer"]

    def _cancel_confirmations(self):
        with self._lock:
            cancelled = list(self._pending)
            for pending in self._pending.values():
                pending["answer"] = False
                pending["event"].set()
            self._events = deque(event for event in self._events if event["kind"] != "confirm")
            if cancelled:
                self._emit("dismiss_confirm", ids=cancelled)

    def configure_logging(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            if getattr(handler, "ddas_plus_handler", False):
                root.removeHandler(handler)
                handler.close()
        root.setLevel(logging.INFO)
        root.addHandler(BridgeLogHandler(self))
        directory = Path(self.settings.settings["log_export_path"])
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(directory / "ddas_plus.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        file_handler.addFilter(DiagnosticLogFilter())
        file_handler.ddas_plus_handler = True
        root.addHandler(file_handler)

    @endpoint
    def bootstrap(self):
        with self._lock:
            for key, pending in self._pending.items():
                if not pending["event"].is_set():
                    self._emit("confirm", id=key, title=pending["title"], text=pending["text"])
        return {"settings": copy.deepcopy(self.settings.settings), "version": APP_VERSION, "profile_ui": "--profile-ui" in sys.argv}

    @endpoint
    def check_update(self):
        request = Request(LATEST_RELEASE_API, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"DDAS-PLUS/{APP_VERSION}",
        })
        try:
            with urlopen(request, timeout=8) as response:
                release = json.load(response)
        except HTTPError as error:
            if error.code == 404:
                raise ValueError("GitHub 上未找到正式发布版本") from error
            raise ValueError(f"GitHub 版本检查失败（HTTP {error.code}）") from error
        except (URLError, TimeoutError) as error:
            raise ValueError("无法连接 GitHub，请检查网络后重试") from error
        except (ValueError, UnicodeError) as error:
            raise ValueError("GitHub 返回的发布信息无法读取") from error

        tag = release.get("tag_name") if isinstance(release, dict) else None
        latest = _version_parts(tag if isinstance(tag, str) else "")
        return {"tag": tag, "available": latest > _version_parts(APP_VERSION)}

    @endpoint
    def open_release(self, tag=None):
        if tag is not None:
            if not isinstance(tag, str):
                raise ValueError("GitHub 发布版本号格式无效")
            _version_parts(tag)
        url = RELEASES_URL if tag is None else f"{RELEASES_URL}/tag/{tag}"
        if not webbrowser.open(url):
            raise ValueError("无法打开浏览器，请手动访问 GitHub 发布页")

    def _bridge(self):
        """Expose only endpoint methods, never native windows, locks or browser objects."""
        names = ('bootstrap', 'check_update', 'open_release', 'poll', 'respond', 'start_task', 'stop_task',
                 'choose_path', 'generate_config', 'expand_image_sources', 'preview_image_config', 'save_image_config',
                 'open_file', 'load_data', 'save_data', 'read_clipboard', 'write_clipboard',
                 'save_settings', 'test_browser', 'import_field_config', 'export_field_config',
                 'download_browser', 'clear_log', 'export_log', 'report_ui_timing')
        return SimpleNamespace(**{name: getattr(self, name) for name in names})

    @endpoint
    def poll(self, timeout_ms=0):
        # The condition releases the API lock while waiting, so clicks and confirmations
        # never queue behind a sleeping poll. Heartbeats are capped at one second.
        deadline = time.monotonic() + min(max(float(timeout_ms), 0), 1000)/1000
        with self._changed:
            while not self._closed:
                running = self._starting or self.runner.is_running()
                state = (running, self.status)
                if self._events or state != self._last_state or time.monotonic() >= deadline:
                    break
                self._changed.wait(timeout=min(.1, max(0, deadline-time.monotonic())))
            # User decisions and result messages must not wait behind a log backlog.
            events, remaining = [], deque()
            for event in self._events:
                if event["kind"] != "log" and len(events) < 150:
                    events.append(event)
                else:
                    remaining.append(event)
            events.extend(remaining.popleft() for _ in range(min(150-len(events), len(remaining))))
            self._events = remaining
            self._last_state = (self._starting or self.runner.is_running(), self.status)
            # Tell the page to stop polling while the window is being torn down. An
            # in-flight JS bridge call whose evaluate_js never gets a main-thread
            # callback is what used to keep a non-daemon thread (and the process) alive.
            return {"events": events, "running": self._last_state[0], "status": self.status,
                    "closed": self._closed}

    @endpoint
    def respond(self, key, answer):
        with self._lock:
            pending = self._pending.get(key)
            if pending:
                pending["answer"] = bool(answer)
                pending["event"].set()

    @endpoint
    def start_task(self, tool, payload):
        with self._lock:
            if self._closed:
                raise ValueError("窗口已关闭")
            if self._starting or self.runner.is_running():
                raise ValueError("PIM 任务已在运行" if tool == "pim" else "任务已在运行")
            self._starting = True
        try:
            callbacks = TaskCallbacks(
                log=logging.info, status=self._status,
                error=lambda text: self._message(text, "错误", "error"),
                warning=lambda text: self._message(text, "警告", "warning"),
                info=lambda text: self._message(text, "任务完成"),
                confirm=lambda text: self._confirm(text, "任务完成" if tool == "deedraw" else "提示"),
            )
            if tool == "deedraw":
                from deedraw.parallel import ParallelTaskProcessor
                default_mode = payload.get('mode', 'add')
                policy = payload.get('conflict_policy')
                fields = []
                for row in payload.get("fields", []):
                    mode = row.get("mode", default_mode)
                    if mode not in ("add", "modify"):
                        raise ValueError("字段的选项操作无效")
                    modify_only = mode == "modify"
                    if not modify_only and 'conflict_policy' in payload and policy not in ('skip', 'overwrite'):
                        raise ValueError('请选择已有选项冲突处理方式')
                    options = row.get("options", [])
                    if not row.get("code", "").strip() or not Path(row.get("file") or "").is_file():
                        raise ValueError("请填写字段名称或编码，并选择有效的配置文件")
                    rename = modify_only and row.get("rename") is True
                    if len(options) != 4 or not (any(options) or rename):
                        raise ValueError("请至少勾选一项执行内容")
                    fields.append(DeedrawFieldRequest(row["code"].strip(), row["file"], *map(bool, options),
                        overwrite_existing=not modify_only and (policy == "overwrite" or (policy is None and payload.get("overwrite_existing") is True)),
                        skip_existing=not modify_only and policy == "skip", modify_only=modify_only, rename_option=rename))
                if not fields:
                    raise ValueError("请至少添加一个字段")
                request = DeedrawTaskRequest(fields, copy.deepcopy(self.settings.settings))
                self.active_task = ParallelTaskProcessor(self.runner, callbacks)
                started = self.active_task.start(request)
            elif tool == "pim":
                from pim.task import PimTask
                options = payload.get("options", [])
                if len(options) != 4:
                    raise ValueError("执行内容无效")
                preset = bool(payload.get("preset"))
                if preset and any(options):
                    raise ValueError("配置预设模块与其他功能不能同时勾选，请只选择一种功能")
                if not payload.get("file"):
                    raise ValueError("未选择配置文件。请先生成或选择配置文件。")
                if not Path(payload["file"]).is_file():
                    raise ValueError("请先选择有效的配置文件")
                if not preset and not any(options):
                    raise ValueError("请至少勾选一项执行内容")
                read_config(payload["file"], options=options, preset=preset)
                request = PimTaskRequest(payload["file"], bool(options[1]), bool(options[3]),
                    bool(options[0]), bool(options[2]), preset,
                    self.settings.settings.get("pim_settings", {}).get("pixel_size", "750"))
                self.runner.stop_event.clear()
                self.active_task = PimTask(request, callbacks, self.runner.stop_event, settings=copy.deepcopy(self.settings.settings))
                started = self.runner.start_task_thread(self.active_task.run)
            else:
                raise ValueError("未知工具")
            if not started:
                raise ValueError("启动任务失败")
            return True
        finally:
            with self._lock:
                self._starting = False

    @endpoint
    def stop_task(self):
        if self._starting or self.runner.is_running():
            self.runner.request_stop()
            self._cancel_confirmations()
            self._status("正在终止...")
            # Do not report completion on the TaskRunner's join timeout: poll actual liveness.
            self.runner.stop_task_thread(self.active_task)
        return True

    def on_closing(self):
        if self._starting or self.runner.is_running():
            self._message("请先停止当前任务，再关闭窗口。", "任务运行中", "warning")
            return False
        with self._lock:
            # _emit() drops every event once _closed is set, so pending confirmations
            # must be released first or their dismiss notice never reaches the page.
            self._cancel_confirmations()
            self._closed = True
            # Wake in-flight long polls immediately instead of leaving them blocked
            # until their 1s deadline while the window is being torn down.
            self._changed.notify_all()
        return True

    def on_closed(self):
        """Final guard for pywebview's non-daemon JS bridge threads.

        Every JS->Python call runs on a plain (non-daemon) thread and returns its
        value through window.evaluate_js(). On macOS WKWebView / Windows WebView2
        that call waits without a timeout for a UI-thread callback. Destroying the
        window during an in-flight poll(1000) can leave the callback unfulfilled,
        so the thread never finishes and interpreter shutdown hangs forever.

        Normal cleanup is still allowed to run first: this daemon watchdog simply
        disappears with the process if shutdown succeeds, and force-exits after a
        short grace period only when a bridge thread is actually stranded.
        """
        with self._lock:
            self._cancel_confirmations()
            self._closed = True
            self._changed.notify_all()

        def force_exit():
            for handler in list(logging.getLogger().handlers):
                try:
                    handler.flush()
                except Exception:
                    pass
            for stream in (sys.stdout, sys.stderr):
                try:
                    stream.flush()
                except Exception:
                    pass
            os._exit(0)

        watchdog = threading.Timer(1.0, force_exit)
        watchdog.daemon = True
        watchdog.start()

    @endpoint
    def choose_path(self, kind="excel"):
        import webview
        if self.window is None:
            raise ValueError("窗口尚未就绪")
        if kind == "image_sources" and sys.platform == "darwin":
            return self._choose_mac_image_sources()
        if kind == "image_sources":
            kind = "images"
        directory = kind == "directory"
        types = {"excel": ("Excel files (*.xlsx)",), "images": ("图片 (*.png;*.jpg;*.jpeg;*.gif)",)}.get(kind, ())
        result = self.window.create_file_dialog(webview.FileDialog.FOLDER if directory else webview.FileDialog.OPEN,
                                               allow_multiple=kind == "images", file_types=types)
        if kind == "images":
            return list(result or ())
        if not result:
            return ""
        path = result[0]
        if kind == "browser" and platform.system() == "Darwin" and path.endswith('.app'):
            path = str(Path(path) / 'Contents/MacOS/Google Chrome')
        return path

    def _choose_mac_image_sources(self):
        from AppKit import NSModalResponseOK, NSOpenPanel
        from PyObjCTools.AppHelper import callAfter

        finished = threading.Event()
        paths, errors = [], []

        def show_panel():
            try:
                panel = NSOpenPanel.openPanel()
                panel.setCanChooseFiles_(True)
                panel.setCanChooseDirectories_(True)
                panel.setAllowsMultipleSelection_(True)
                panel.setAllowedFileTypes_(["png", "jpg", "jpeg", "gif"])
                if panel.runModal() == NSModalResponseOK:
                    paths.extend(str(url.path()) for url in panel.URLs())
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()

        callAfter(show_panel)
        finished.wait()
        if errors:
            raise errors[0]
        return paths

    def bind_image_drop(self):
        # pywebview supplies absolute paths through its native DOM drop event.
        from webview.dom import DOMEventHandler
        self.window.dom.body.events.drop += DOMEventHandler(
            self._on_image_drop, prevent_default=True,
        )

    def _on_image_drop(self, event):
        from urllib.parse import unquote
        from webview.dom import _dnd_state

        files = event.get("dataTransfer", {}).get("files", [])
        # WKWebView can omit folders from FileList or report a different
        # name than pywebview's native drop bridge uses to match the path.
        pending = _dnd_state["paths"]
        unmatched = [unquote(path) for _, path in pending if Path(unquote(path)).is_dir()]
        pending.clear()
        paths = [file["pywebviewFullPath"] for file in files if file.get("pywebviewFullPath")]
        paths.extend(path for path in unmatched if path not in paths)
        payload = json.dumps({
            "paths": paths, "count": len(files),
            "x": event.get("clientX"), "y": event.get("clientY"),
        })
        self.window.evaluate_js(
            f"window.dispatchEvent(new CustomEvent('config-image-drop', {{detail: {payload}}}))"
        )

    @endpoint
    def expand_image_sources(self, paths):
        images = scan_images(paths, recursive=True, add_prefix=True,
                             include_source_name=True, invalid_files=[])
        return [{"path": str(path.resolve()), "prefixed_name": name} for path, name in images]

    @endpoint
    def preview_image_config(self, pc, mobile=None, add_prefix=False, pairs=None):
        def images(entries):
            for entry in entries:
                path = Path(entry["path"])
                if not path.is_file() or not is_supported_image(path):
                    raise ValueError(f"图片不可用：{path}")
                yield path, entry["prefixed_name"] if add_prefix else path.stem

        if mobile is None:
            return [config_row(path, name) for path, name in images(pc)]
        return paired_rows(images(pc), images(mobile), pairs)

    @endpoint
    def save_image_config(self, rows, text_only=False, tool="deedraw"):
        headers = PIM_HEADERS if tool == "pim" else DEEDRAW_HEADERS
        if text_only:
            headers = headers[:3]
        if not rows or any(len(row) != len(headers) or
                           any(not isinstance(value, str) for value in row) for row in rows):
            raise ValueError("配置预览没有有效数据")
        directory = Path(self.settings.settings["config_path"])
        kind = "文本" if text_only else "图片"
        output = directory / f"{kind}配置_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx"
        write_config_rows(output, headers, rows)
        logging.info("配置文件已生成: %s，选项 %s 行", output, len(rows))
        return str(output)

    @endpoint
    def generate_config(self, tool, directories=None, add_prefix=False, mobile_sources=None):
        if directories is None:
            folder = self.choose_path("directory")
            if not folder["ok"]:
                raise ValueError(folder["message"])
            if not folder["value"]:
                return ""
            sources = [Path(folder["value"])]
        else:
            if tool != "deedraw" or not isinstance(directories, list):
                raise ValueError("图片来源无效")
            if mobile_sources is not None and not isinstance(mobile_sources, list):
                raise ValueError("移动图来源无效")
            all_sources = directories + (mobile_sources or [])
            if not all_sources:
                raise ValueError("请至少添加一张图片或一个目录")
            for path in all_sources:
                if not isinstance(path, str) or not path.strip():
                    raise ValueError("图片来源无效")
                source = Path(path)
                if not source.is_dir() and not (source.is_file() and is_supported_image(source)):
                    raise ValueError(f"图片来源不可用：{source}")
            sources = [Path(path) for path in directories]
        first = (sources or [Path(mobile_sources[0])])[0]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        if tool == "deedraw":
            prefix = bool(add_prefix)
            if directories is None:
                prefix = any(p.is_dir() for p in first.iterdir()) and self._confirm(
                    "是否将每一级子文件夹的名称添加到选项值名称前缀？")
            name = first.name if first.is_dir() else first.stem
            output = Path(self.settings.settings["config_path"]) / f"{name}_{stamp}_data.xlsx"
            result = generate_config_workbook(
                sources[0] if sources else None, output, DEEDRAW_HEADERS,
                recursive=True, add_prefix=prefix, additional_dirs=sources[1:],
                include_source_name=directories is not None, mobile_sources=mobile_sources,
            )
        elif tool == "pim":
            output = first / f"PimScript_{stamp}.xlsx"
            result = generate_config_workbook(first, output, PIM_HEADERS)
        else:
            raise ValueError("未知工具")
        logging.info("配置文件已生成: %s，选项 %s 行，跳过 %s 个非图片文件", output,
                     result["image_count"], len(result["invalid_files"]))
        return str(output)

    @endpoint
    def open_file(self, path):
        if not path:
            raise ValueError("未选择文件")
        if not Path(path).exists():
            raise ValueError("请先选择有效的配置文件")
        if platform.system() == "Windows":
            os.startfile(path)
        else:
            subprocess.run(["open" if platform.system() == "Darwin" else "xdg-open", path], check=True)

    @endpoint
    def report_ui_timing(self, stage, milliseconds):
        # Opt-in diagnostics contain timings only, never field or clipboard data.
        if '--profile-ui' not in sys.argv:
            return
        if stage not in ('event-delivery', 'click-paint', 'bridge', 'event-loop'):
            raise ValueError('无效的计时类型')
        value = float(milliseconds)
        if not 0 <= value <= 3600000:
            raise ValueError('无效的计时值')
        logging.info('[UI timing] %s %.1f ms', stage, value)

    @endpoint
    def read_clipboard(self):
        from common.clipboard import clipboard_text
        return clipboard_text()

    @endpoint
    def write_clipboard(self, text):
        if not isinstance(text, str):
            raise ValueError('剪贴板内容必须为文本')
        from common.clipboard import clipboard_text
        return clipboard_text(text)

    @endpoint
    def load_data(self, path, include_rename=False):
        if not path or not Path(path).is_file():
            raise ValueError("请先选择有效的配置文件")
        workbook = openpyxl.load_workbook(path, data_only=False)
        try:
            sheet = workbook.active
            headers = [cell.value for cell in sheet[1]]
            if not validate_headers(headers, allow_text=True):
                raise ValueError("配置文件应包含：选项名（或选项值名称）、PC选项值、移动选项值、PC图路径、移动图路径")
            width = 6 if headers[5:6] == [RENAME_HEADER] else min(len(headers), 5)
            headers = headers[:width]
            if include_rename and width<6:
                headers = [headers[0], *VALUE_HEADERS, RENAME_HEADER]
                width = 6
            rows = [["" if value is None else str(value) for value in row[:width]]
                    for row in sheet.iter_rows(min_row=2, max_col=width, values_only=True)]
            token = uuid.uuid4().hex
            self._editor_versions[token] = (str(Path(path).resolve()), Path(path).stat().st_mtime_ns)
            return {"headers": headers, "rows": rows, "token": token}
        finally:
            workbook.close()

    @endpoint
    def save_data(self, path, rows, token):
        if not rows:
            raise ValueError("没有可保存的数据")
        version = self._editor_versions.get(token)
        if not version or version != (str(Path(path).resolve()), Path(path).stat().st_mtime_ns):
            raise ValueError("文件已被其他程序修改，请重新打开后编辑")
        workbook = openpyxl.load_workbook(path)
        try:
            sheet = workbook.active
            headers = [cell.value for cell in sheet[1]]
            if not validate_headers(headers, allow_text=True):
                raise ValueError("配置格式不兼容")
            width = 6 if headers[5:6] == [RENAME_HEADER] else min(len(headers), 5)
            if width<6 and all(isinstance(row, list) and len(row)==6 for row in rows):
                if len(headers)>5:
                    raise ValueError("第 6 列已被占用，无法添加「新选项名」")
                for column, header in enumerate([*VALUE_HEADERS, RENAME_HEADER], 2):
                    sheet.cell(1, column, header)
                width = 6
            if any(not isinstance(row, list) or len(row) != width for row in rows):
                raise ValueError("配置数据列数与表头不一致")
            for row in sheet.iter_rows(min_row=2, max_col=width):
                for cell in row:
                    cell.value = None
            for index, row in enumerate(rows, 2):
                for column, value in enumerate(row, 1):
                    cell = sheet.cell(index, column, value)
                    if cell.data_type == "f":
                        cell.data_type = "s"
            temporary = Path(path).with_name(f".{Path(path).stem}.{uuid.uuid4().hex}.xlsx")
            try:
                workbook.save(temporary)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            self._editor_versions[token] = (version[0], Path(path).stat().st_mtime_ns)
        finally:
            workbook.close()
        self._message("数据已保存", "成功")

    @endpoint
    def save_settings(self, values):
        if self._starting or self.runner.is_running():
            raise ValueError("请先停止当前任务，再修改设置。")
        new = copy.deepcopy(self.settings.settings)
        for key in ("log_export_path", "task_result_path", "config_path", "chrome_path"):
            value = str(values.get(key, "")).strip()
            if not value:
                raise ValueError("路径设置不能为空")
            if key != "chrome_path":
                Path(value).mkdir(parents=True, exist_ok=True)
            new[key] = value
        pixel = values.get("pim_settings", {}).get("pixel_size", "750")
        if pixel not in ("750", "790"):
            raise ValueError("默认像素大小无效")
        new["pim_settings"] = {"pixel_size": pixel}
        new["browser_settings"] = {"auto_close": bool(values.get("browser_settings", {}).get("auto_close"))}
        # Write explicitly so a filesystem error is surfaced instead of swallowed by legacy Settings.
        destination = Path(self.settings.settings_file)
        temporary = destination.with_name(f'.settings.{uuid.uuid4().hex}.tmp')
        try:
            temporary.write_text(json.dumps(new, ensure_ascii=False, indent=4), encoding='utf-8')
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        self.settings.settings = new
        self.configure_logging()
        self._message("设置已保存", "成功")
        return copy.deepcopy(new)

    @endpoint
    def test_browser(self, path):
        from common.browser import BrowserInitializer
        if not path or not Path(path).exists():
            raise ValueError("请选择有效的 Chrome 浏览器路径")
        initializer = BrowserInitializer()
        success, message = initializer.test_browser(path)
        self._message(message, "成功" if success else "错误", "info" if success else "error")

    @endpoint
    def download_browser(self):
        from common.browser import open_chrome_download
        open_chrome_download()

    @endpoint
    def clear_log(self):
        with self._lock:
            self._log_text.clear()
            self._events = deque(e for e in self._events if e["kind"] != "log")

    @staticmethod
    def _field_config(data):
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("不支持的多字段配置 JSON 格式")
        mode = data.get("mode")
        fields = data.get("fields")
        if mode not in ("add", "modify") or not isinstance(fields, list) or not fields:
            raise ValueError("多字段配置缺少有效的模式或字段")
        normalized = []
        for index, field in enumerate(fields, 1):
            if not isinstance(field, dict):
                raise ValueError(f"第 {index} 个字段格式无效")
            code, file, options = field.get("code"), field.get("file"), field.get("options")
            rename = field.get("rename", False)
            if (not isinstance(code, str) or not isinstance(file, str) or
                    not isinstance(options, list) or len(options) != 4 or
                    any(type(option) is not bool for option in options) or type(rename) is not bool):
                raise ValueError(f"第 {index} 个字段的名称、路径或勾选项格式无效")
            entry = dict(code=code, file=file, options=options, rename=rename)
            if "mode" in field:
                if field["mode"] not in ("add", "modify"):
                    raise ValueError(f"第 {index} 个字段的选项操作无效")
                entry["mode"] = field["mode"]
            normalized.append(entry)
        config = dict(version=1, mode=mode, fields=normalized)
        if "pim" in data:
            pim = data["pim"]
            if not isinstance(pim, dict):
                raise ValueError("PIM 配置格式无效")
            file, options, preset = pim.get("file"), pim.get("options"), pim.get("preset")
            if (not isinstance(file, str) or not isinstance(options, list) or len(options) != 4 or
                    any(type(option) is not bool for option in options) or type(preset) is not bool or
                    (preset and any(options))):
                raise ValueError("PIM 配置的路径、勾选项或预设模块无效")
            config["pim"] = dict(file=file, options=options, preset=preset)
        return config

    @endpoint
    def import_field_config(self):
        import webview
        if self.window is None:
            raise ValueError("窗口尚未就绪")
        result = self.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                               file_types=("JSON files (*.json)",))
        if not result:
            return None
        path = Path(result if isinstance(result, str) else result[0])
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeError) as error:
            raise ValueError("无法读取 JSON，请选择有效的多字段配置文件") from error
        return self._field_config(data)

    @endpoint
    def export_field_config(self, data):
        import webview
        if self.window is None:
            raise ValueError("窗口尚未就绪")
        config = self._field_config(data)
        result = self.window.create_file_dialog(webview.FileDialog.SAVE,
                                               save_filename="DDAS配置.json", allow_multiple=False,
                                               file_types=("JSON files (*.json)",))
        if not result:
            return ""
        path = Path(result if isinstance(result, str) else result[0])
        if path.suffix.lower() != ".json":
            path = path.with_name(path.name + ".json")
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return str(path)

    @endpoint
    def export_log(self):
        import webview
        if self.window is None:
            raise ValueError("窗口尚未就绪")
        directory = Path(self.settings.settings["log_export_path"])
        result = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(directory) if directory.is_dir() else '',
            save_filename=f"log_{datetime.now():%Y%m%d_%H%M%S}.txt",
            allow_multiple=False,
            file_types=("Text files (*.txt)",),
        )
        if not result:
            return ""
        path = Path(result if isinstance(result, str) else result[0])
        with self._lock:
            text = '\n'.join(self._log_text)
        path.write_text(text, encoding='utf-8')
        self._message(f"日志已导出到:\n{path}", "成功")
        return str(path)
