from DrissionPage.errors import ContextLostError, ElementLostError, JavaScriptError
from common.execution_audit import HttpAudit
from deedraw.save_confirmation import SaveConfirmation
from deedraw.upload_state import read_upload_state, backfill_complete
from deedraw.forbidden_words import request_forbidden_words, is_forbidden_prompt
import os
import json
import logging
import time
import threading
from pathlib import Path
from deedraw.page_state import SubmissionUnknown, validate_option_name, validate_upload_image, saved_location, read_options, form_feedback, is_option_edit_url, reset_option_form
import openpyxl
from common.browser import create_browser, close_browser
from common.task_models import TaskCallbacks, TaskResult, TaskCancelled
from common.config_loader import read_config
from common.task_results import TaskReport, format_task_report, report_result, publish_result
from deedraw.field_lookup import resolve_field, read_field_snapshot


class DuplicateOption(ValueError):
    pass


class DeedrawTask:
    """深绘业务任务入口：浏览器初始化、元素操作、填写与图片上传。"""

    def __init__(self, request, callbacks):
        self.request = request
        self.callbacks = callbacks

    def run(self, execute):
        self.callbacks.status("正在执行")
        try:
            return execute(self.request) or TaskResult(False, "任务未返回执行结果")
        except Exception as error:
            self.callbacks.error(str(error))
            return TaskResult(False, str(error))


class TaskProcessor:

    LOGIN_URL = 'https://www.deepdraw.biz/login'
    AUTHORIZED_PREFIX = 'https://www.deepdraw.biz/authorized/'
    FIELD_SETTINGS_URL = 'https://www.deepdraw.biz/authorized/merchant/setting/productFields'

    def __init__(self, task_runner, callbacks):
        """纯业务处理器，只通过回调报告状态，不持有界面或控件。"""
        self.browser = None
        self.running = True  # 默认运行状态
        self.thread = None

        self.task_runner = task_runner
        self.callbacks = callbacks

        self.settings = None

    def start(self, request):
        """启动任务处理；request 是 View 创建的不可变任务快照。"""
        try:
            self.request = request
            self.settings = request.settings
            task = DeedrawTask(request, self.callbacks)

            # 启动任务线程
            if self.task_runner.start_task_thread(
                target=lambda: task.run(self.run_task),
                args=()
            ):
                logging.info("任务已启动")
                return True
            else:
                return False

        except Exception as e:
            error_msg = f"启动任务时出错: {str(e)}"
            logging.error(error_msg)
            return False

    def run_task(self, request):
        """Validate all fields first; preserve actual failures through the terminal result."""
        self.request = request
        self.settings = request.settings
        self.running = True
        result = None
        try:
            self._configs = {id(row): read_config(row.config_path, options=(
                row.upload_pc_image, row.fill_pc_value, row.upload_mobile_image, row.fill_mobile_value
            ), rename_option=row.rename_option, allow_blank_content=row.modify_only) for row in request.fields}
            if not request.fields:
                raise ValueError("请至少添加一个字段")
            for field in request.fields:
                seen_names = set()
                for number, values in self._configs[id(field)]:
                    try:
                        validate_option_name(values[0])
                        if field.rename_option:
                            validate_option_name(values[5])
                        if values[0] in seen_names:
                            raise ValueError('配置中有重复选项名，请先合并或修改')
                        seen_names.add(values[0])
                        for selected, column in ((field.upload_pc_image, 3), (field.upload_mobile_image, 4)):
                            if selected and values[column]:
                                validate_upload_image(values[column])
                    except ValueError as error:
                        raise ValueError(f'第 {number} 行：{error}') from error
            chrome_path = self.settings.get('chrome_path')
            if not chrome_path:
                raise ValueError("请先在设置中配置浏览器路径")
            self._check_stop()
            self.update_status("正在初始化浏览器...")
            if not self.initialize_browser(chrome_path):
                raise RuntimeError("浏览器初始化失败")
            self._check_stop()
            self.update_status("正在登录...")
            if not self.login():
                raise RuntimeError(getattr(self, '_login_error', '登录失败'))
            result = self.process_task()
        except TaskCancelled:
            result = TaskResult(False, "任务已终止", {"cancelled": True})
        except Exception as error:
            logging.error("执行任务时出错: %s", error)
            result = TaskResult(False, str(error))
        finally:
            self.running = False
            self.cleanup_browser()
        publish_result(self.callbacks, result)
        if self.callbacks.finished:
            self.callbacks.finished()
        return result

    def _check_stop(self):
        if self.is_stop_requested():
            raise TaskCancelled()

    def _pause(self, seconds):
        if self.task_runner.stop_event.wait(seconds):
            raise TaskCancelled()

    def show_error(self, message):
        """在主线程中显示错误消息"""
        logging.error(message)
        self.callbacks.error(message)
        self.update_status("就绪")

    def get_field_tabindex(self, field_code, timeout=8):
        """Wait for a stable list and cross-check the actual add-option link."""
        self._check_stop()
        self.browser.wait.doc_loaded()
        deadline = time.monotonic()+timeout
        previous = None
        last_error = None
        while True:
            self._check_stop()
            try:
                snapshot = read_field_snapshot(self.browser)
                if snapshot.get('ready'):
                    fields = snapshot['fields']
                    signature = json.dumps(fields, ensure_ascii=False, sort_keys=True)
                    if signature == previous:
                        number = resolve_field(field_code, fields)
                        self._row_log(logging.INFO, '字段定位确认：%s → 编号 %s；已核对容器、tabindex和新增链接', field_code, number)
                        return number
                    previous = signature
                else:
                    previous = None
            except TaskCancelled:
                raise
            except Exception as error:
                last_error = error
                previous = None
            if time.monotonic() >= deadline:
                if isinstance(last_error, ValueError):
                    raise last_error
                raise ValueError(f'字段列表未就绪或未能可靠定位“{field_code}”，请确认登录状态及字段列表')
            self._pause(.2)

    def login(self, timeout=600):
        """Wait for user login in the visible Chrome window; never read or fill credentials."""
        try:
            self._check_stop()
            self.browser.get(self.LOGIN_URL)
            self.browser.wait.doc_loaded()
            deadline = time.monotonic() + timeout
            announced = False
            while True:
                self._check_stop()
                if str(self.browser.url).startswith(self.AUTHORIZED_PREFIX):
                    logging.info("已检测到登录成功")
                    return self.open_field_settings()
                if not announced:
                    self.update_status("请在浏览器中登录深绘，登录后自动继续")
                    logging.info("请在浏览器中输入账号密码，完成登录后任务将自动继续")
                    announced = True
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待登录超时，请重新开始任务并在浏览器中完成登录")
                self._pause(.3)
        except TaskCancelled:
            raise
        except Exception as error:
            self._login_error = str(error)
            logging.error("登录失败: %s", error)
            return False

    def open_field_settings(self):
        """进入字段设置页并确认登录状态仍有效。"""
        self.browser.get(self.FIELD_SETTINGS_URL)
        self.browser.wait.doc_loaded()
        if str(self.browser.url).startswith(self.AUTHORIZED_PREFIX):
            return True
        raise Exception("登录状态已失效，无法进入字段设置页")

    def process_task(self):
        self._success_rows, self._failure_rows = [], []
        self._skipped_rows, self._overwritten_rows, self._modified_rows = [], [], []
        self._http_stats = {}
        self._uncertain_rows = []
        started = time.monotonic()
        total = sum(len(rows) for rows in self._configs.values())
        try:
            for row in self.request.fields:
                self._check_stop()
                self.process_single_field(row, row.code, self._success_rows, self._failure_rows)
        except (TaskCancelled, SubmissionUnknown):
            pass
        self._report = TaskReport(total, len(self._success_rows), len(self._failure_rows),
            time.monotonic()-started,
            [f"{field} - {number}: {value}" for field,number,value in self._success_rows],
            [f"{field} - {number}: {reason}" for field,number,reason in self._failure_rows],
            **self.conflict_report_details())
        result = report_result(self._report, cancelled=self.is_stop_requested())
        result.details['http'] = self._http_stats
        result.details['uncertain_rows'] = list(self._uncertain_rows)
        if self._uncertain_rows:
            result.message += '\n提交结果待确认：\n'+'\n'.join(self._uncertain_rows)+'\n已暂停后续执行，请核对页面后再运行。'
        logging.info('[HTTP] 深绘任务汇总：%s', self._http_stats)
        return result

    def conflict_report_details(self):
        return {
            'skipped_details': [f'{field} - {row}: {value}' for field, row, value in self._skipped_rows],
            'modified_details': [f'{field} - {row}: {value}' for field, row, value in self._modified_rows],
            'overwritten_details': [f'{field} - {row}: {value}' for field, row, value in self._overwritten_rows],
        }

    def _record_skip(self, field_code, number, value, reason="已有选项"):
        self._skipped_rows.append((field_code, number, value if reason=="已有选项" else f"{value}（{reason}）"))
        self._row_log(logging.INFO, '跳过%s：%s', reason, value)

    def process_single_field(self, row_info, field_code, completed_task_info, failed_task_info):
        modify_only = getattr(row_info, 'modify_only', False) is True
        rename = modify_only and getattr(row_info, 'rename_option', False) is True
        rows = getattr(self, '_configs', {}).get(id(row_info))
        if rows is None:
            rows = read_config(row_info.config_path, options=(row_info.upload_pc_image,
                row_info.fill_pc_value, row_info.upload_mobile_image, row_info.fill_mobile_value),
                rename_option=rename, allow_blank_content=modify_only)
        overwrite = getattr(row_info, 'overwrite_existing', False) is True
        skip_existing = getattr(row_info, 'skip_existing', False) is True
        if not hasattr(self, '_skipped_rows'):
            self._skipped_rows, self._overwritten_rows, self._modified_rows = [], [], []
        matches = {}
        try:
            self._check_stop()
            self.browser.get(self.FIELD_SETTINGS_URL)
            self.browser.wait.doc_loaded()
            field_tabindex = self.get_field_tabindex(field_code)
            if not field_tabindex:
                raise ValueError(f"未找到字段 {field_code} 对应的单元格或字段编号")
            existing = read_options(self.browser, field_tabindex)
            if existing is None:
                if overwrite or modify_only:
                    raise ValueError('字段选项列表未就绪，无法匹配已有选项')
                existing = []
                self._row_log(logging.INFO, '字段选项HTML未就绪，名称重复由页面服务端校验')
            if overwrite or skip_existing or modify_only:
                for item in existing:
                    matches.setdefault(item['value'], {})[item['id']] = item
                found = sum(values[0] in matches for _, values in rows)
                if modify_only:
                    self._row_log(logging.INFO, '修改模式：%s 条匹配已有选项，%s 条未找到', found, len(rows)-found)
                else:
                    self._row_log(logging.INFO, '冲突处理：%s；%s 条同名，%s 条走新增', '覆盖' if overwrite else '跳过', found, len(rows)-found)
        except TaskCancelled:
            raise
        except Exception as error:
            failed_task_info.extend((field_code, number, str(error)) for number,_ in rows)
            return
        for index, (number, values) in enumerate(rows, 1):
            self._check_stop()
            self._current_row = (field_code, number)
            try:
                self.update_status(f"正在处理字段 {field_code} 的第 {index}/{len(rows)} 条数据")
                targets = matches.get(values[0], {})
                if modify_only and not targets:
                    self._record_skip(field_code, number, values[0], '未找到待修改选项')
                    continue
                submitted_name = values[5] if rename else values[0]
                if skip_existing and targets and not modify_only:
                    self._record_skip(field_code, number, values[0])
                    continue
                target_errors = []
                for target in targets.values() if targets else (None,):
                    self._check_stop()
                    try:
                        confirmation = SaveConfirmation()
                        with HttpAudit(self.browser, f"深绘 字段 {field_code} 第 {number} 行", getattr(self, "_http_stats", None), request_observer=confirmation):
                            validate_option_name(submitted_name)
                            before_ids = {item['id'] for item in existing}
                            option_id = ''
                            if target is not None:
                                if not confirmation.save_monitoring:
                                    raise ValueError('编辑保存确认监听不可用，未修改该选项')
                                edit_url = target.get('edit_url')
                                option_id = target['id']
                                if not is_option_edit_url(edit_url, field_tabindex, option_id):
                                    raise ValueError('未找到当前选项对应的修改入口')
                                self._row_log(logging.INFO, '%s现有选项：%s（ID %s）', '修改' if modify_only else '覆盖', values[0], option_id)
                                self.browser.get(edit_url)
                            else:
                                self.browser.get(f'https://www.deepdraw.biz/authorized/merchant/setting/productField/{field_tabindex}/addOption')
                            self.browser.wait.doc_loaded()
                            self._check_stop()
                            if option_id:
                                if not is_option_edit_url(self.browser.url, field_tabindex, option_id):
                                    raise ValueError('编辑表单与目标选项不符')
                                if modify_only:
                                    selected = [rename, row_info.fill_pc_value, row_info.fill_mobile_value,
                                                row_info.upload_pc_image, row_info.upload_mobile_image]
                                    cleared = reset_option_form(self.browser, values[0], selected)
                                else:
                                    cleared = reset_option_form(self.browser, values[0])
                                if not cleared:
                                    raise ValueError('编辑表单与目标选项不符，或无法清空旧内容')
                            else:
                                confirmation.expect_name(field_tabindex, values[0])
                            if not modify_only or rename:
                                self.handle_value(submitted_name)
                            if not option_id:
                                self.check_option_name(confirmation)
                            if row_info.fill_pc_value and values[1]:
                                self.handle_pc_options(values[1])
                            if row_info.fill_mobile_value and values[2]:
                                self.handle_mobile_options(values[2])
                            self.check_forbidden_words([values[1] if row_info.fill_pc_value else '', values[2] if row_info.fill_mobile_value else ''])
                            if row_info.upload_pc_image and values[3] and not self.pc_upload_file(values[3]):
                                raise RuntimeError("PC图片上传失败或超时")
                            if row_info.upload_mobile_image and values[4] and not self.mobile_upload_file(values[4]):
                                raise RuntimeError("移动图片上传失败或超时")
                            self._check_stop()
                            if option_id:
                                self.submit_and_verify(field_tabindex, submitted_name, before_ids, confirmation=confirmation,
                                                       option_id=option_id)
                            else:
                                existing = self.submit_and_verify(field_tabindex, values[0], before_ids, confirmation=confirmation)
                    except DuplicateOption:
                        raise
                    except (SubmissionUnknown, TaskCancelled):
                        raise
                    except Exception as error:
                        if target is None:
                            raise
                        reason = f"选项 ID {target['id']}：{error}"
                        self._row_log(logging.ERROR, '%s', reason)
                        target_errors.append(reason)
                if target_errors:
                    raise RuntimeError('；'.join(target_errors))
                detail = f'{values[0]} → {submitted_name}' if submitted_name != values[0] else values[0]
                completed_task_info.append((field_code, number, detail))
                if modify_only:
                    self._modified_rows.append((field_code, number, detail))
                    self._row_log(logging.INFO, '修改成功：%s（%s 个选项）', detail, len(targets))
                elif targets:
                    self._overwritten_rows.append((field_code, number, values[0]))
                    self._row_log(logging.INFO, '覆盖成功：%s（%s 个同名选项）', values[0], len(targets))
            except DuplicateOption as error:
                if skip_existing:
                    self._record_skip(field_code, number, values[0])
                else:
                    failed_task_info.append((field_code, number, f"{values[0]}：{error}"))
            except SubmissionUnknown as error:
                detail = f'字段 {field_code} 第 {number} 行：{error}'
                if not hasattr(self, '_uncertain_rows'):
                    self._uncertain_rows = []
                self._uncertain_rows.append(detail)
                self._row_log(logging.WARNING, '提交结果未知 %s；暂停后续处理', detail)
                raise
            except TaskCancelled:
                raise
            except Exception as error:
                failed_task_info.append((field_code, number, f"{values[0]}：{error}"))
                logging.error("字段 %s - 第 %s 行失败: %s", field_code, number, error)
            finally:
                self._current_row = None

    def cleanup_browser(self):
        """清理浏览器资源"""
        keep_open = bool(getattr(self, '_uncertain_rows', [])) or (not self.is_stop_requested() and not (self.settings or {}).get('browser_settings', {}).get('auto_close', False))
        self.browser = close_browser(self.browser, keep_open=keep_open)

    def update_status(self, message):
        """更新状态显示"""
        self.callbacks.status(message)

    def update_ui_after_stop(self):
        """停止后更新UI"""
        self.callbacks.status("已终止")

    def initialize_browser(self, chrome_path):
        """初始化浏览器"""
        try:
            self.browser = create_browser(chrome_path, mute=True, load_timeout=30)
            logging.info("浏览器初始化成功")
            return True

        except Exception as e:
            error_msg = f"浏览器初始化失败: {str(e)}"
            logging.error(error_msg)
            return False

    def _row_log(self, level, message, *args):
        row = getattr(self, '_current_row', None)
        context = f'字段 {row[0]} 第 {row[1]} 行 | ' if row else '深绘 | '
        logging.log(level, '[逐行结果] '+context+message, *args)

    def check_option_name(self, confirmation, timeout=10):
        if not confirmation.validation_monitoring:
            raise ValueError('名称查重接口监听不可用，未提交该行')
        try:
            self.browser.run_js("if(!window.jQuery||!window.validator)throw Error('校验器未就绪');jQuery('#value').trigger('blur');jQuery('#value').valid();")
            deadline = time.monotonic()+timeout
            while time.monotonic() < deadline:
                self._check_stop()
                if confirmation.name_done.is_set():
                    if confirmation.name_result is False:
                        self._row_log(logging.WARNING, '名称查重接口返回false：名称重复，不执行上传和提交')
                        raise DuplicateOption('字段选项名称重复（接口返回false）')
                    if confirmation.name_result is True:
                        self._row_log(logging.INFO, '名称查重接口返回true：当前字段及名称校验通过')
                        return
                    raise ValueError('名称查重接口响应异常，未提交该行')
                self._pause(.1)
        except (ValueError, TaskCancelled):
            raise
        except Exception as error:
            raise ValueError('名称查重接口校验失败，未提交该行') from error
        raise ValueError('名称查重接口等待超时，未提交该行')

    def check_forbidden_words(self, contents):
        self._check_stop()
        try:
            hits = request_forbidden_words(self.browser, contents)
        except Exception as error:
            self._check_stop()
            self._row_log(logging.WARNING, '违禁词接口校验未完成，跳过该行：%s', error)
            raise ValueError(f'违禁词接口校验未完成：{error}') from error
        self._check_stop()
        if hits:
            self._row_log(logging.WARNING, '违禁词接口命中：%s', '、'.join(hits))
            self._row_log(logging.INFO, '违禁词按默认策略继续，页面同类确认框将自动确认')
        else:
            self._row_log(logging.INFO, '违禁词接口检查通过（无文本内容或响应为空）')
        return hits

    def submit_and_verify(self, field_id, value, before_ids, timeout=30, confirmation=None, option_id=""):
        has_content = self.browser.run_js("""
            const form = document.querySelector('#mainForm');
            const fields = ['textInputOfPc', 'filePathOfPc', 'textInputOfMobile', 'filePathOfMobile']
                .map(id => form?.querySelector('#' + id));
            if (fields.some(field => !field)) return null;
            if (!fields.some(field => field.value.trim() !== '')) return false;
            // Sync page validation with the final draft before submitting.
            form.querySelectorAll('textarea,#value').forEach(field => {
                field.dispatchEvent(new Event('change', {bubbles:true}));
                field.dispatchEvent(new Event('blur', {bubbles:true}));
            });
            return true;
        """)
        if has_content is False:
            raise ValueError('手机端和PC端至少填写一个')
        if has_content is not True:
            raise ValueError('无法读取深绘表单的 PC 和移动端内容')
        submit = self.browser.ele('css:span.button_submit3', timeout=3)
        if not submit:
            raise RuntimeError('未找到提交按钮')
        try:
            if confirmation is not None:
                if option_id:
                    confirmation.arm(field_id, value, option_id)
                else:
                    confirmation.arm(field_id, value)
            submit.click()
            deadline = time.monotonic()+timeout
            handled_dialog = False
            while time.monotonic() < deadline:
                self._check_stop()
                if confirmation is not None and confirmation.confirmed.is_set():
                    return []
                if confirmation is not None and confirmation.server_error is not None:
                    break
                try:
                    returned = saved_location(self.browser.url, field_id)
                    if returned:
                        options = read_options(self.browser, field_id) if not option_id else None
                        if options is not None and any(item['id'] not in before_ids and item['value'] == value for item in options):
                            return options
                    else:
                        feedback = form_feedback(self.browser)
                except (ContextLostError, ElementLostError, JavaScriptError):
                    # The form document can disappear before the redirect reaches the listener.
                    self._pause(.2)
                    continue
                if not returned:
                    if feedback['errors'] and not feedback.get('pending'):
                        raise ValueError('页面校验失败：'+'；'.join(feedback['errors']))
                    if feedback['dialog']:
                        if feedback['confirm'] and not handled_dialog:
                            if not is_forbidden_prompt(feedback['dialog']):
                                raise ValueError('出现未识别的确认弹窗，未自动点击：'+feedback['dialog'])
                            self._row_log(logging.WARNING, '触发违禁词页面弹窗：%s', feedback['dialog'])
                            self._check_stop()
                            clicked = self.browser.run_js("""
                                const text=arguments[0];
                                const dialog=Array.from(document.querySelectorAll('.bootbox-confirm')).find(e=>
                                  e.getClientRects().length&&(e.querySelector('.bootbox-body')?.textContent||'').trim()===text);
                                const button=dialog?.querySelector('button[data-bb-handler="confirm"]');
                                if(!button)return false;
                                button.click();return true;
                            """, feedback['dialog'])
                            if not clicked:
                                raise ValueError('未找到当前违禁词弹窗的确认按钮')
                            handled_dialog = True
                            self._row_log(logging.WARNING, '已默认确认违禁词弹窗：%s', feedback['dialog'])
                        elif not feedback['confirm']:
                            raise ValueError('页面提示：'+feedback['dialog'])
                self._pause(.2)
        except (ValueError, TaskCancelled):
            raise
        except Exception as error:
            logging.warning('提交等待异常，将回查选项：%s', error)
        if confirmation is not None and confirmation.confirmed.is_set():
            return []
        if confirmation is not None and confirmation.server_error is not None:
            operation = f'修改选项 {option_id}' if option_id else '新增选项'
            raise SubmissionUnknown(f'{operation}时保存接口返回 HTTP {confirmation.server_error}，是否写入待确认，不自动重试')
        if option_id:
            raise SubmissionUnknown(f'未确认选项 {option_id} 的修改是否保存，不自动重试')
        self._row_log(logging.WARNING, '未获取匹配的303保存确认，尝试HTML回查；不重复提交')
        # Never click submit again. A late server response may already have created it.
        try:
            self._check_stop()
            self.browser.get(self.FIELD_SETTINGS_URL)
            self.browser.wait.doc_loaded()
            if confirmation is not None and confirmation.confirmed.is_set():
                return []
            options = read_options(self.browser, field_id)
            if options is not None and any(item['id'] not in before_ids and item['value'] == value for item in options):
                self._row_log(logging.INFO, '超时回查确认新增选项已保存')
                return options
        except TaskCancelled:
            raise
        except Exception as error:
            logging.warning('保存结果回查异常：%s', error)
        if confirmation is not None and confirmation.confirmed.is_set():
            return []
        raise SubmissionUnknown('未确认新增选项是否保存，不自动重试')

    def pc_upload_file(self, file_path):
        return self._upload_image(file_path, 'Pc')

    def mobile_upload_file(self, file_path):
        return self._upload_image(file_path, 'Mobile')

    def _upload_image(self, file_path, platform):
        label = 'PC' if platform == 'Pc' else '移动'
        try:
            image = validate_upload_image(file_path)
            self._check_stop()
            file_input = self.browser.ele(f'#fileToUploadOf{platform}_1', timeout=5)
            if not file_input:
                raise RuntimeError('未找到文件输入框')
            before = read_upload_state(self.browser, platform)
            if not before.get('present'):
                raise RuntimeError('图片回填控件未就绪')
            # The supplied page binds change on mainForm; only these two globals
            # are needed for its upload callback. Do not patch HTMLElement.click.
            self.browser.run_js("if(typeof currentSortNum==='undefined'||typeof addImage==='undefined')throw Error('上传组件未就绪');addImage=false;currentSortNum='1';")
            file_input.input(str(image))
            timeout = float((self.settings or {}).get('upload_timeout', 30))
            deadline = time.monotonic()+max(5, min(timeout, 120))
            while time.monotonic() < deadline:
                self._check_stop()
                state = read_upload_state(self.browser, platform)
                if state['errors']:
                    raise RuntimeError('；'.join(state['errors']))
                if backfill_complete(before, state):
                    self._row_log(logging.INFO, '%s图片新路径已回填、预览地址匹配；%s', label, '预览已加载' if state.get('loaded') else '预览尚未加载完成，不影响上传结果')
                    return True
                self._pause(.2)
            raise TimeoutError(f'{label}图片上传超时（{timeout:g}秒）')
        except TaskCancelled:
            raise
        except Exception as error:
            logging.error('%s图片上传失败：%s', label, error)
            return False

    def handle_pc_options(self, option_text):
        """PC端选项处理"""
        try:
            # 等待PC端选项输入框出现
            option_input = self.browser.ele('#textInputOfPc', timeout=10)
            if option_input:
                option_input.clear()
                option_input.input(option_text)
            else:
                raise Exception("未找到PC端选项输入框")
        except Exception as e:
            logging.error(f"PC端选项处理失败: {str(e)}")
            raise

    def handle_mobile_options(self, option_text):
        """移动端选项处理"""
        try:
            # 等待移动端选项输入框出现
            option_input = self.browser.ele('#textInputOfMobile', timeout=10)
            if option_input:
                option_input.clear()
                option_input.input(option_text)
            else:
                raise Exception("未找到移动端选项输入框")
        except Exception as e:
            logging.error(f"移动端选项处理失败: {str(e)}")
            raise

    def handle_value(self, value_text):
        """选项名称处理"""
        try:
            # 等待选项名称输入框出现
            value_input = self.browser.ele('#value', timeout=10)
            if value_input:
                value_input.clear()
                value_input.input(value_text)
            else:
                raise Exception("未找到选项名称输入框")
        except Exception as e:
            logging.error(f"选项名称处理失败: {str(e)}")
            raise

    def is_stop_requested(self):
        return self.task_runner.stop_event.is_set()

    def request_stop(self):
        """响应公共任务管理器的终止请求并释放浏览器。"""
        self.task_runner.stop_event.set()
        self.running = False
        self.update_status("正在终止...")
        # The worker owns browser cleanup; do not race page operations from another thread.

    stop_task = request_stop
