import os
import logging
import time
import threading
import openpyxl
from common.browser import create_browser, close_browser
from common.task_models import TaskCallbacks, TaskResult
from common.task_results import TaskReport, format_task_report
from common.result_exporter import export_task_results


class DeedrawTask:
    """深绘业务任务入口：浏览器初始化、元素操作、填写与图片上传。"""

    def __init__(self, request, callbacks):
        self.request = request
        self.callbacks = callbacks

    def run(self, execute):
        self.callbacks.status("正在执行")
        try:
            return execute(self.request) or TaskResult(True, "任务完成")
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

    def handle_confirm_button(self):
        """处理确认按钮点击（DrissionPage版本）"""
        try:
            # 检测错误弹窗
            confirm_btn = self.browser.ele('xpath://button[@data-bb-handler="confirm"]', timeout=1)
            if confirm_btn:
                confirm_btn.click()
                return True
        except Exception as e:
            logging.warning(f"处理确认按钮时出错: {str(e)}")
        return False

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
        """在线程中运行的完整任务流程"""
        self.request = request
        self.running = True
        final_status = "执行失败"
        try:
            # 检查浏览器路径
            chrome_path = self.settings.get('chrome_path')
            if not chrome_path:
                self.show_error("请先在设置中配置浏览器路径")
                return TaskResult(False, "未配置浏览器路径")

            # 更新任务状态
            self.update_status("正在初始化浏览器...")

            # 初始化浏览器
            if not self.initialize_browser(chrome_path):
                self.show_error("浏览器初始化失败")
                return TaskResult(False, "浏览器初始化失败")

            # 登录
            self.update_status("正在登录...")
            if not self.login():
                if self.browser:
                    self.browser.quit()
                    self.browser = None
                return TaskResult(False, "登录失败")

            # 执行主要任务
            self.process_task()
            if self.is_stop_requested():
                final_status = "已终止"
                return TaskResult(False, "任务已终止", {"cancelled": True})
            final_status = "任务已完成"
            return TaskResult(True, "任务完成")

        except Exception as e:
            error_msg = f"执行任务时出错: {str(e)}"
            logging.error(error_msg)
            self.show_error(error_msg)
            return TaskResult(False, error_msg)
        finally:
            self.cleanup_browser()
            if self.is_stop_requested():
                final_status = "已终止"
            self.update_status(final_status)
            if self.callbacks.finished:
                self.callbacks.finished()

    def show_error(self, message):
        """在主线程中显示错误消息"""
        logging.error(message)
        self.callbacks.error(message)
        self.update_status("就绪")

    def get_field_tabindex(self, field_code):
        """获取字段的tabindex"""
        try:

            # 等待页面加载
            self.browser.wait.doc_loaded()
            time.sleep(1)

            # 使用data-pinyin属性查找字段
            field_td = self.browser.ele(f'xpath://td[@data-pinyin="{field_code}"]')

            if not field_td:
                logging.error(f"未找到字段 {field_code} 对应的单元格")
                return None


            # 获取父级tbody元素的id
            tbody = field_td.parent('tag:tbody')

            if not tbody:
                logging.error("未找到父级tbody元素")
                return None


            # 从tbody的id中提取tabindex
            tbody_id = tbody.attr('id')
            if not tbody_id:
                logging.error("tbody元素没有id属性")
                return None


            # 提取数字部分
            tabindex = tbody_id.replace('fieldContainer', '')

            # 构造并打印新的URL
            new_url = f'https://www.deepdraw.biz/authorized/merchant/setting/productField/{tabindex}/addOption'

            return tabindex

        except Exception as e:
            logging.error(f"获取字段tabindex时出错: {str(e)}")
            return None

    def login(self):
        """进入深绘后台：复用有效 Cookie，仅在出现登录表单时提交账号密码。"""
        try:
            self.browser.get(self.LOGIN_URL)
            self.browser.wait.doc_loaded()

            username_input = None
            deadline = time.time() + 10
            while time.time() < deadline and not self.is_stop_requested():
                if str(self.browser.url).startswith(self.AUTHORIZED_PREFIX):
                    logging.info("已检测到有效登录状态")
                    return self.open_field_settings()
                username_input = self.browser.ele('#credential', timeout=0.5)
                if username_input:
                    break
                time.sleep(0.2)

            if not username_input:
                raise Exception("既未进入后台，也未检测到登录表单")

            username = self.request.username
            password = self.request.password
            if not username or not password:
                raise ValueError("当前 Cookie 已失效，请输入账号和密码")

            password_input = self.browser.ele('#password', timeout=2)
            if not password_input:
                raise Exception("未找到密码输入框")

            username_input.clear()
            username_input.input(username)
            password_input.clear()
            password_input.input(password)

            login_button = self.browser.ele(
                'xpath://span[contains(@class, "btnLogin")]', timeout=2
            )
            if not login_button:
                raise Exception("未找到登录按钮")
            login_button.click()

            deadline = time.time() + 15
            while time.time() < deadline and not self.is_stop_requested():
                if str(self.browser.url).startswith(self.AUTHORIZED_PREFIX):
                    logging.info("登录成功")
                    return self.open_field_settings()
                time.sleep(0.2)
            raise Exception("登录失败，未跳转到后台页面")

        except ValueError as e:
            logging.error(f'登录失败: {str(e)}')
            self.callbacks.error(str(e))
            return False
        except Exception as e:
            logging.error(f'登录失败: {str(e)}')
            self.callbacks.error(f"登录失败: {str(e)}")
            return False

    def open_field_settings(self):
        """进入字段设置页并确认登录状态仍有效。"""
        self.browser.get(self.FIELD_SETTINGS_URL)
        self.browser.wait.doc_loaded()
        if str(self.browser.url).startswith(self.AUTHORIZED_PREFIX):
            return True
        raise Exception("登录状态已失效，无法进入字段设置页")

    def process_task(self):
        """处理所有字段行的任务"""
        logging.info("深绘批量任务开始")
        self.running = True  # 确保任务开始时设置为运行状态

        # 首先初始化所有需要的变量
        total_tasks = 0
        completed_task_info = []  # 初始化为空列表
        failed_task_info = []    # 初始化为空列表
        start_time = time.time()

        try:
            # 首先计算总任务数
            for row_info in self.request.fields:
                field_code = row_info.code
                if not field_code:
                    continue

                # 读取Excel文件获取行数
                try:
                    wb = openpyxl.load_workbook(row_info.config_path)
                    sheet = wb.active
                    # 减去标题行
                    row_count = sheet.max_row - 1
                    total_tasks += row_count
                    wb.close()
                except Exception as e:
                    logging.error(f"计算字段 {field_code} 的任务数时出错: {str(e)}")
                    continue

            # 处理每个字段
            for row_info in self.request.fields:
                if self.is_stop_requested():
                    logging.info("任务已终止")
                    break

                field_code = row_info.code
                if not field_code:
                    continue

                # 处理单个字段
                self.process_single_field(row_info, field_code, completed_task_info, failed_task_info)

            # 显示结果
            self.show_final_results(total_tasks, len(completed_task_info), len(failed_task_info),
                                  completed_task_info, failed_task_info, start_time)

        except Exception as e:
            logging.error(f"执行批量任务时出错: {str(e)}")
            self.callbacks.error(f"执行批量任务时出错: {str(e)}")
            self.update_status("执行出错")
        finally:
            self.running = False
            self.cleanup_browser()
            logging.info("任务已终止" if self.is_stop_requested() else "深绘批量任务完成")

    def process_single_field(self, row_info, field_code, completed_task_info, failed_task_info):
        """处理单个字段的逻辑"""
        try:
            logging.info(f"开始处理字段: {field_code}")  # 添加调试信息
            # 检查浏览器状态并重新初始化
            self.browser.refresh()
            self.browser.wait.doc_loaded()  # 等待页面加载完成

            # 打开字段设置页面
            self.browser.get('https://www.deepdraw.biz/authorized/merchant/setting/productFields')
            self.browser.wait.doc_loaded()
            time.sleep(2)  # 额外等待时间

            # 获取字段的tabindex
            field_tabindex = self.get_field_tabindex(field_code)
            if not field_tabindex:
                logging.error(f'字段 {field_code} 获取tabindex失败，跳过当前字段')
                return

            logging.info(f'字段 {field_code} 的tabindex为: {field_tabindex}')

            # 设置复选框状态
            # 读取Excel文件
            wb = openpyxl.load_workbook(row_info.config_path)
            sheet = wb.active
            data_rows = list(sheet.iter_rows(min_row=2, values_only=True))

            # 处理每一行数据
            for i, row_data in enumerate(data_rows, start=2):
                if self.is_stop_requested():
                    logging.info("任务已终止，停止处理数据")
                    break

                try:
                    self.update_status(f"正在处理字段 {field_code} 的第 {i-1}/{len(data_rows)} 条数据")

                    # 构造目标URL
                    target_url = f'https://www.deepdraw.biz/authorized/merchant/setting/productField/{field_tabindex}/addOption'
                    self.browser.get(target_url)

                    # 等待页面加载完成
                    self.browser.wait.doc_loaded()

                    # 处理选项名称
                    self.handle_value(row_data[0])

                    # 根据复选框选择执行相应操作
                    if row_info.fill_pc_value:
                        self.handle_pc_options(row_data[1])
                    if row_info.fill_mobile_value:
                        self.handle_mobile_options(row_data[2])
                    if row_info.upload_pc_image:
                        self.pc_upload_file(row_data[3])
                    if row_info.upload_mobile_image:
                        self.mobile_upload_file(row_data[4])

                    # 点击保存按钮
                    submit_button = self.browser.ele('xpath://span[contains(@class, "button_submit3")]')
                    if submit_button:
                        submit_button.click()

                        # 点击提交后立即检查是否需要处理确认按钮
                        if row_info.fill_pc_value or row_info.fill_mobile_value:
                            self.handle_confirm_button()

                        # 添加提交成功校验
                        start_time = time.time()
                        success = False
                        while time.time() - start_time < 5:  # 最多等待5秒
                            if f'lastOperatedFieldId={field_tabindex}' in self.browser.url:
                                success = True
                                break
                            time.sleep(0.1)

                        if success:
                            completed_task_info.append((field_code, i-1, row_data[0]))
                        else:
                            failed_task_info.append((field_code, i-1, row_data[0]))
                            logging.error(f'字段 {field_code} - 第 {i-1} 条数据提交失败，未检测到提交成功URL')
                            continue
                    else:
                        raise Exception("未找到保存按钮")

                except Exception as e:
                    failed_task_info.append((field_code, i-1, row_data[0]))
                    logging.error(f'字段 {field_code} - 处理第 {i-1} 条数据时出错: {str(e)}')

            wb.close()
            logging.info(f'字段 {field_code} 处理完成')

        except Exception as e:
            logging.error(f'处理字段 {field_code} 时出错: {str(e)}')

    def show_final_results(self, total_tasks, completed_tasks, failed_tasks,
                          completed_task_info, failed_task_info, start_time):
        """显示任务执行结果"""
        duration = time.time() - start_time
        minutes = int(duration // 60)
        seconds = duration % 60
        report = TaskReport(
            total_tasks, completed_tasks, failed_tasks, duration,
            [f"{field} - {row}: {content}" for field, row, content in completed_task_info],
            [f"{field} - {row}: {reason}" for field, row, reason in failed_task_info],
        )
        message = format_task_report(report)

        # 在主线程中显示结果
        def show_results():
            try:
                if self.callbacks.confirm and self.callbacks.confirm(message + "\n\n是否导出执行结果到Excel文件？"):
                    export_task_results(
                        self.settings, total_tasks, completed_tasks, failed_tasks,
                        completed_task_info, failed_task_info, minutes, seconds,
                    )
                else:
                    self.update_status("任务已完成")
            except Exception as e:
                logging.error(f"显示结果时出错: {str(e)}")

        show_results()

    def cleanup_browser(self):
        """清理浏览器资源"""
        keep_open = not self.settings.get('browser_settings', {}).get('auto_close', False)
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
            self.callbacks.error(error_msg)
            return False

    def pc_upload_file(self, file_path):
        """PC端上传文件（优化版）"""
        try:

            # 1. 等待页面加载完成
            self.browser.wait.doc_loaded()

            # 2. 通过JavaScript模拟触发imageAdd的点击事件
            self.browser.run_js('''
                var event = new MouseEvent('click', {
                    'view': window,
                    'bubbles': true,
                    'cancelable': true
                });
                // 阻止默认行为(阻止文件选择框弹出)
                var originalClick = HTMLElement.prototype.click;
                HTMLElement.prototype.click = function() {
                    // 不执行实际的点击
                };
                // 触发事件
                document.querySelector('div.pcImages a[name="imageAdd"]').dispatchEvent(event);
                // 恢复原始click方法
                HTMLElement.prototype.click = originalClick;
            ''')

            # 3. 等待文件输入框出现
            file_input = self.browser.ele('#fileToUploadOfPc_1', timeout=5)
            if not file_input:
                logging.error("未找到文件输入框")
                return False

            # 4. 确保上传组件已初始化完成
            time.sleep(1)

            # 5. 设置文件路径
            file_input.input(file_path)

            # 6. 优化等待上传完成的逻辑
            start_time = time.time()
            while time.time() - start_time < 5:  # 减少最大等待时间到5秒
                # 首先检查上传是否完成，因为这是最常见的情况
                file_path_input = self.browser.ele('xpath://input[@id="filePathOfPc"]', timeout=0.05)
                if file_path_input and file_path_input.attr('value'):
                    file_path_value = file_path_input.attr('value')

                    # 检查图片是否成功加载，减少等待时间
                    img_element = self.browser.ele(f'xpath://div[contains(@class, "pcImages")]//img[contains(@src, "{file_path_value}")]', timeout=1)
                    if img_element:
                        return True

                # 其次检查是否有错误，因为这种情况较少
                error_dialog = self.browser.ele('xpath://div[contains(@class, "bootbox-alert")]', timeout=0.05)
                if error_dialog:
                    error_text = error_dialog.text
                    logging.error(f"上传出现错误: {error_text}")
                    ok_button = self.browser.ele('xpath://div[contains(@class, "bootbox-alert")]//button[contains(text(), "确定")]')
                    if ok_button:
                        ok_button.click()
                    return False

                time.sleep(0.05)  # 进一步减少轮询间隔

            logging.error("文件上传超时")
            return False

        except Exception as e:
            logging.error(f"PC端上传文件失败: {str(e)}")
            return False

    def mobile_upload_file(self, file_path):
        """移动端上传文件（优化版）"""
        try:

            # 1. 等待页面加载完成
            self.browser.wait.doc_loaded()

            # 2. 通过JavaScript模拟触发imageAdd的点击事件
            self.browser.run_js('''
                var event = new MouseEvent('click', {
                    'view': window,
                    'bubbles': true,
                    'cancelable': true
                });
                // 阻止默认行为(阻止文件选择框弹出)
                var originalClick = HTMLElement.prototype.click;
                HTMLElement.prototype.click = function() {
                    // 不执行实际的点击
                };
                // 触发事件
                document.querySelector('div.mobileImages a[name="imageAdd"]').dispatchEvent(event);
                // 恢复原始click方法
                HTMLElement.prototype.click = originalClick;
            ''')

            # 3. 等待文件输入框出现
            file_input = self.browser.ele('#fileToUploadOfMobile_1', timeout=5)
            if not file_input:
                logging.error("未找到文件输入框")
                return False

            # 4. 确保上传组件已初始化完成
            time.sleep(1)

            # 5. 设置文件路径
            file_input.input(file_path)

            # 6. 优化等待上传完成的逻辑
            start_time = time.time()
            while time.time() - start_time < 5:  # 减少最大等待时间到5秒
                # 首先检查上传是否完成，因为这是最常见的情况
                file_path_input = self.browser.ele('xpath://input[@id="filePathOfMobile"]', timeout=0.05)
                if file_path_input and file_path_input.attr('value'):
                    file_path_value = file_path_input.attr('value')

                    # 检查图片是否成功加载，减少等待时间
                    img_element = self.browser.ele(f'xpath://div[contains(@class, "mobileImages")]//img[contains(@src, "{file_path_value}")]', timeout=1)
                    if img_element:
                        return True

                # 其次检查是否有错误，因为这种情况较少
                error_dialog = self.browser.ele('xpath://div[contains(@class, "bootbox-alert")]', timeout=0.05)
                if error_dialog:
                    error_text = error_dialog.text
                    logging.error(f"上传出现错误: {error_text}")
                    ok_button = self.browser.ele('xpath://div[contains(@class, "bootbox-alert")]//button[contains(text(), "确定")]')
                    if ok_button:
                        ok_button.click()
                    return False

                time.sleep(0.05)  # 进一步减少轮询间隔

            logging.error("文件上传超时")
            return False

        except Exception as e:
            logging.error(f"移动端上传文件失败: {str(e)}")
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
        self.browser = close_browser(self.browser, log=logging.info)

    stop_task = request_stop
