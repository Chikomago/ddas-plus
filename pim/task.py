"""PIM automation with validated snapshots and one terminal result per run."""
from common.execution_audit import HttpAudit, audit_http
import logging
import os
import time
import threading
from common.browser import create_browser, close_browser
from common.settings import Settings as AppSettings
from common.config_loader import read_config
from common.task_models import PimTaskRequest, TaskCallbacks, TaskResult, TaskCancelled
from common.task_results import TaskReport, report_result, publish_result


class PimTask:
    NEW = 'xpath://button[@class="pmdm-btn pmdm-btn-primary"]/span[text()="新 建"]/..'
    PRESET_INPUT = 'xpath://input[@placeholder="请输入" and @class="pmdm-input"]'
    PRESET_SAVE = 'xpath://button[@type="button" and @class="pmdm-btn pmdm-btn-primary"]/span[text()="确 定"]/..'
    PRESET_CANCEL = 'xpath://button[@type="button" and @class="pmdm-btn"]/span[text()="取 消"]/..'

    def __init__(self, request: PimTaskRequest, callbacks: TaskCallbacks, stop_event=None, settings=None):
        self.request, self.callbacks = request, callbacks
        self.stop_flag = stop_event or threading.Event()
        self.page = None
        self.settings = settings
        self._close_override = None

    def confirm(self, message):
        self._check_stop()
        answer = self.callbacks.confirm(message) if self.callbacks.confirm else True
        self._check_stop()
        return answer

    def notify_error(self, message):
        self.callbacks.error(message)

    def notify_warning(self, message):
        (self.callbacks.warning or self.callbacks.log)(message)

    def notify_info(self, message):
        (self.callbacks.info or self.callbacks.log)(message)

    def load_settings(self):
        settings = AppSettings()
        settings.load_settings()
        return settings.settings

    def close_page(self, keep_open=False):
        self.page = close_browser(self.page, keep_open=keep_open, log=logging.info)

    def _check_stop(self):
        if self.stop_flag.is_set():
            raise TaskCancelled()

    def _pause(self, seconds):
        if self.stop_flag.wait(seconds):
            raise TaskCancelled()

    def _required(self, selector, message, timeout=3):
        self._check_stop()
        element = self.page.ele(selector, timeout=timeout)
        if not element:
            raise RuntimeError(message)
        return element

    def _wait(self, predicate, timeout, message):
        deadline = time.monotonic()+timeout
        while True:
            self._check_stop()
            if predicate():
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(message)
            self._pause(.2)

    def _closed_dialog(self, selector):
        element = self.page.ele(selector, timeout=.2)
        return not element or not element.states.is_displayed

    def run(self):
        self.callbacks.status('正在执行')
        result = None
        try:
            if self.settings is None:
                self.settings = self.load_settings()
            result = self.run_task_logic(self.request)
            if not isinstance(result, TaskResult):
                raise RuntimeError('任务未返回执行结果')
        except TaskCancelled:
            result = getattr(self, '_cancelled_result', None) or TaskResult(False, '任务已终止', {'cancelled': True})
        except Exception as error:
            logging.error('PIM任务失败: %s', error)
            result = TaskResult(False, str(error))
        finally:
            if self.page:
                auto = (self.settings or {}).get('browser_settings', {}).get('auto_close', False)
                close = self.stop_flag.is_set() or (auto if self._close_override is None else self._close_override)
                self.close_page(keep_open=not close)
        publish_result(self.callbacks, result)
        if self.callbacks.finished:
            self.callbacks.finished()
        return result

    def request_stop(self):
        self.stop_flag.set()
        self.callbacks.status('正在终止...')
        # Cleanup belongs to the worker, never to a competing UI/stop thread.

    def initialize_chrome_driver(self):
        try:
            settings = self.settings if self.settings is not None else self.load_settings()
            path = settings.get('chrome_path') or settings.get('browser_path')
            if path and not os.path.exists(path):
                raise ValueError('请选择有效的 Chrome 浏览器路径')
            self._check_stop()
            self.page = create_browser(path, mute=True, load_timeout=30)
            self._check_stop()
            return True
        except TaskCancelled:
            raise
        except Exception as error:
            raise RuntimeError(f'未能初始化 DrissionPage: {error}\n请检查浏览器设置') from error

    def run_task_logic(self, request):
        options = (request.upload_pc_image, request.fill_pc_value, request.upload_mobile_image, request.fill_mobile_value)
        if request.preset_module and any(options):
            raise ValueError('配置预设模块与其他功能不能同时勾选，请只选择一种功能')
        if not request.config_path:
            raise ValueError('未选择配置文件。请先生成或选择配置文件。')
        if not request.preset_module and not any(options):
            raise ValueError('请至少勾选一项执行内容')
        self._rows = read_config(request.config_path, options=options, preset=request.preset_module)
        if not self.initialize_chrome_driver():
            raise RuntimeError('浏览器初始化失败')
        self._check_stop()
        if request.preset_module:
            return self._run_preset(request)
        self.callbacks.status('请在浏览器中登录 PIM 并打开选项设置页')
        self.page.get('https://pimboss.leycloud.com/')
        logging.info('请登录PIMBoss，打开文案列表-选择账号配置映射-添加文案字段-选择组件类型')
        self._wait(lambda: any('选项设置' in element.text for element in self.page.eles('.ant-modal-title', timeout=.5)),
                   600, "未能找到'选项设置'页面，请确认页面是否正确打开")
        if not self.confirm('已到选项设置页，是否进行字段配置？'):
            return TaskResult(False, '用户取消字段配置', {'cancelled': True})
        return self.configure_fields(request)

    def _run_preset(self, request):
        self.callbacks.status('请在浏览器中登录 PIM，登录后自动继续')
        self.page.get('https://pim.leycloud.com/')
        self._wait(lambda: str(self.page.url).startswith(('https://pim.leycloud.com/home', 'https://pim.leycloud.com/product/')), 600, '登录超时，请手动确认')
        self._wait(lambda: str(self.page.url).startswith('https://pim.leycloud.com/product/setting/detail-page/preset'),
                   300, '等待超时，未检测到预设模块页面URL')
        if not self.confirm("已检测到预设模块页面，请确保当前选择模块正确，是否继续执行'新建'名称流程？"):
            return TaskResult(False, '用户选择不执行任务，任务取消', {'cancelled': True})
        started = time.monotonic()
        succeeded, failures = 0, []
        http_stats = {}
        for index, (number, values) in enumerate(self._rows):
            try:
                with HttpAudit(self.page, f"PIM 预设 第 {number} 行", http_stats):
                    self._check_stop()
                    self._required(self.NEW, "未找到'新建'按钮，请确认页面是否正确。").click()
                    self._required(f'css:input[type="radio"].pmdm-radio-input[value="{request.pixel_size}"]',
                                   f'未能找到 {request.pixel_size}px 按钮').click()
                    field = self._required(self.PRESET_INPUT, '等待超时，未检测到输入框', timeout=10)
                    field.clear()
                    field.input(values[0])
                    self._required(self.PRESET_SAVE, "未找到'确定'按钮").click()
                    self._wait(lambda: self._closed_dialog(self.PRESET_INPUT), 10, '提交未确认：新建名称对话框没有关闭')
                    succeeded += 1
            except TaskCancelled:
                result = report_result(TaskReport(len(self._rows), succeeded, len(failures),
                    time.monotonic()-started, failure_details=failures), cancelled=True)
                self._cancelled_result = result
                raise
            except Exception as error:
                failures.append(f'第 {number} 行 {values[0]}：{error}')
                logging.error('%s', failures[-1])
                # Recovery must establish an empty/closed dialog before another create.
                try:
                    if not self._closed_dialog(self.PRESET_INPUT):
                        self._required(self.PRESET_CANCEL, "未找到'取消'按钮，无法恢复任务").click()
                        self._wait(lambda: self._closed_dialog(self.PRESET_INPUT), 5, '无法关闭失败的对话框')
                except TaskCancelled:
                    raise
                except Exception as recovery_error:
                    failures.extend(f'第 {n} 行 {v[0]}：未执行，恢复失败：{recovery_error}' for n,v in self._rows[index+1:])
                    break
        result = report_result(TaskReport(len(self._rows), succeeded, len(failures),
            time.monotonic()-started, failure_details=failures))
        result.details['http'] = http_stats
        logging.info('[HTTP] PIM预设任务汇总：%s', http_stats)
        # Preserve the original explicit browser-close choice in preset mode.
        self._close_override = self.confirm('操作完成。\n是否关闭浏览器？')
        return result

    def _fill(self, selector, value, label):
        element = self._required(selector, f'未找到{label}输入框')
        element.clear()
        element.input(value)

    def _upload(self, index, platform, path):
        key = 'PC' if platform == 'PC' else 'MT'
        wrapper = self._required(f'#upload-wrap{key}Value{index}', f'未找到{platform}上传按钮容器')
        upload = wrapper.ele('css:.moxie-shim-html5 > input[type="file"][accept="image/jpeg,image/png"]', timeout=3)
        if not upload:
            raise RuntimeError('未找到文件上传输入框')
        upload.input(path)
        def completed():
            image = self.page.ele(f'css:.ant-form-item-children:has(#upload-wrap{key}Value{index}) img', timeout=.3)
            return bool(image and 'kuaimai-sheji-prod' in (image.attr('src') or ''))
        self._wait(completed, 15, f'{platform}图片上传超时')

    @audit_http('page', 'PIM 配置批次（统一提交，多行共用响应）')
    def configure_fields(self, request):
        rows = getattr(self, '_rows', None)
        if rows is None:
            rows = read_config(request.config_path, options=(request.upload_pc_image,
                request.fill_pc_value, request.upload_mobile_image, request.fill_mobile_value))
        started = time.monotonic()
        try:
            for index, (number, values) in enumerate(rows):
                self._check_stop()
                row_started = time.monotonic()
                logging.info('[逐行结果] PIM 第 %s 行开始', number)
                self.callbacks.status(f'正在配置第 {index+1}/{len(rows)} 条数据')
                self._fill(f'#ComponentType_name{index}', values[0], '选项名称')
                if request.fill_pc_value:
                    self._fill(f'#ComponentType_PCValue{index}', values[1], 'PC选项值')
                if request.fill_mobile_value:
                    self._fill(f'#ComponentType_MTValue{index}', values[2], '移动选项值')
                if request.upload_pc_image:
                    self._upload(index, 'PC', values[3])
                if request.upload_mobile_image:
                    self._upload(index, '移动', values[4])
                logging.info('[逐行结果] PIM 第 %s 行已填入，等待批次提交 | 耗时 %.2fs', number, time.monotonic()-row_started)
                if index < len(rows)-1:
                    add = self.page.ele('css:.ant-modal-body > div > form + a', timeout=1)
                    if not add:
                        add = self.page.ele('css:.ant-modal-body a:contains("+ 新增选项")', timeout=1)
                    if not add:
                        raise RuntimeError('未能找到新增选项按钮')
                    add.click()
                    self._required(f'#ComponentType_name{index+1}', '新增选项未出现')
            self._check_stop()
            self._required('text:确 定', "未找到'确定'按钮，提交未确认").click()
            self._wait(lambda: self._closed_dialog('css:.ant-modal-title'), 10,
                       '提交未确认：选项设置对话框没有关闭')
            for number, _ in rows:
                logging.info('[逐行结果] PIM 第 %s 行提交已确认（批次对话框关闭）', number)
            return report_result(TaskReport(len(rows), len(rows), 0, time.monotonic()-started))
        except TaskCancelled:
            self._cancelled_result = report_result(TaskReport(len(rows), 0, 0,
                time.monotonic()-started), cancelled=True)
            raise
        except Exception as error:
            # These fields are staged in one dialog; without confirmed save none is a confirmed success.
            for number, _ in rows:
                logging.error('[逐行结果] PIM 第 %s 行未确认提交: %s', number, error)
            reasons = [f'第 {number} 行 {values[0]}：未提交，{error}' for number,values in rows]
            return report_result(TaskReport(len(rows), 0, len(rows), time.monotonic()-started,
                                            failure_details=reasons))
